"""Decision API against migrated PostgreSQL and a real Redis projection."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

from argus.apps.decision_api.main import app
from argus.apps.decision_api.service import DecisionService, PaymentDecisionInput
from argus.events.envelope import EventEnvelope
from argus.events.fraud import (
    AccountCreatedPayload,
    PaymentAttemptedPayload,
    PaymentFailedPayload,
)
from argus.features.redis_projection import create_redis_client
from argus.persistence import schema as s
from argus.persistence.database import create_engine
from argus.persistence.repository import PostgresDecisionRepository

T = datetime(2026, 1, 2, tzinfo=UTC)
TIME = "2026-01-02T00:00:00Z"


def payload(prefix, *, amount=100, device=True):
    return {
        "facts": {
            "user": {"user_id": f"{prefix}-user", "created_at": TIME},
            "transaction": {
                "transaction_id": f"{prefix}-transaction",
                "user_id": f"{prefix}-user",
                "merchant_id": "merchant",
                "amount": {"amount_minor": amount, "currency": "usd"},
                "created_at": TIME,
            },
            "payment_attempt": {
                "payment_id": f"{prefix}-payment",
                "transaction_id": f"{prefix}-transaction",
                "attempted_at": TIME,
            },
            "devices": [{"device_id": f"{prefix}-device", "first_seen_at": TIME}]
            if device
            else [],
            "observed_device_id": f"{prefix}-device" if device else None,
        }
    }


def post(client, body, key):
    return client.post(
        "/v1/decisions/payment", json=body, headers={"Idempotency-Key": key}
    )


def event(kind, prefix, *, at=T, device=None):
    if kind == "account.created":
        fact = AccountCreatedPayload(user_id=f"{prefix}-user", device_id=device)
        subject = fact.user_id
    elif kind == "payment.attempted":
        fact = PaymentAttemptedPayload(
            payment_id=str(uuid4()), transaction_id="event-t", user_id=f"{prefix}-user"
        )
        subject = fact.payment_id
    else:
        fact = PaymentFailedPayload(
            payment_id=str(uuid4()), transaction_id="event-t", user_id=f"{prefix}-user"
        )
        subject = fact.payment_id
    return EventEnvelope[type(fact)](
        event_id=uuid4(),
        event_type=kind,
        event_version=1,
        occurred_at=at,
        produced_at=T,
        producer="test",
        trace_id="test",
        subject_id=subject,
        payload=fact,
    )


@pytest.fixture
def api(monkeypatch):
    redis_url = os.environ.get("ARGUS_REDIS_URL")
    if not redis_url or not os.environ.get("ARGUS_DATABASE_URL"):
        pytest.fail("ARGUS_REDIS_URL and ARGUS_DATABASE_URL are required")
    namespace = f"argus:features:v1:test:{uuid4().hex}:"
    monkeypatch.setenv("ARGUS_FEATURE_NAMESPACE", namespace)
    client = create_redis_client(redis_url)
    try:
        with TestClient(app) as http:
            yield http, app.state.projection
    finally:
        keys = list(client.scan_iter(f"{namespace}*"))
        if keys:
            client.delete(*keys)
        client.close()


def test_decisions_evidence_replay_and_conflicts(api):
    http, projection = api
    invalid = payload(str(uuid4()))
    invalid["facts"]["risk_signals"] = []
    assert post(http, invalid, str(uuid4())).status_code == 422
    invalid = payload(str(uuid4()))
    invalid["facts"]["observed_device_id"] = "unobserved"
    assert post(http, invalid, str(uuid4())).status_code == 422
    assert http.get("/health/live").status_code == 200
    assert http.get("/health/ready").status_code == 503
    assert (
        post(http, payload(str(uuid4())), str(uuid4())).json()["error"]["code"]
        == "FEATURES_UNAVAILABLE"
    )
    projection.begin_rebuild()
    assert http.get("/health/ready").status_code == 503
    prefix = str(uuid4())
    body = payload(prefix)
    projection.apply(event("account.created", prefix, device=f"{prefix}-device"))
    projection.mark_ready()
    assert http.get("/health/ready").status_code == 200
    key = str(uuid4())
    first = post(http, body, key)
    assert first.status_code == 200, first.text
    assert first.json()["decision"]["action"] == "ALLOW"
    assert first.json()["decision"]["rule_set_version"] == 2
    assert first.json()["decision"]["policy_version"] == 1
    with create_engine(os.environ["ARGUS_DATABASE_URL"]).connect() as connection:
        record = PostgresDecisionRepository(connection).get(
            first.json()["decision"]["decision_id"]
        )
        assert [
            (x.code, x.value, x.source, x.observed_at)
            for x in record.context.risk_signals
        ] == [
            ("payments_10m", 0, "redis_features_v1", T),
            ("failed_payments_1h", 0, "redis_features_v1", T),
            ("accounts_on_device", 1, "redis_features_v1", T),
        ]
    for _ in range(5):
        projection.apply(event("payment.attempted", prefix))
    replay = post(http, body, key)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["decision"] == first.json()["decision"]
    changed = payload(prefix, amount=101)
    conflict = post(http, changed, key)
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    )
    challenge = post(http, body, str(uuid4()))
    assert (
        challenge.status_code == 200
        and challenge.json()["decision"]["action"] == "CHALLENGE"
    )
    # Changing an already recorded immutable fact is a separate conflict.
    other = post(http, changed, str(uuid4()))
    assert (
        other.status_code == 409
        and other.json()["error"]["code"] == "AUTHORITATIVE_FACT_CONFLICT"
    )


def test_review_missing_device_and_event_time(api):
    http, projection = api
    projection.begin_rebuild()
    prefix = str(uuid4())
    projection.apply(event("payment.attempted", prefix, at=T - timedelta(minutes=10)))
    for _ in range(3):
        projection.apply(event("payment.failed", prefix, at=T - timedelta(minutes=5)))
    projection.mark_ready()
    response = post(http, payload(prefix), str(uuid4()))
    assert response.status_code == 200, response.text
    assert response.json()["decision"]["action"] == "REVIEW"
    assert "FAILED_PAYMENT_VELOCITY_HIGH" in response.json()["decision"]["reason_codes"]
    with create_engine(os.environ["ARGUS_DATABASE_URL"]).connect() as connection:
        record = PostgresDecisionRepository(connection).get(
            response.json()["decision"]["decision_id"]
        )
        assert [(x.code, x.value) for x in record.context.risk_signals][:2] == [
            ("payments_10m", 0),
            ("failed_payments_1h", 3),
        ]
    missing = post(http, payload(str(uuid4()), device=False), str(uuid4()))
    assert (
        missing.status_code == 200 and missing.json()["decision"]["action"] == "REVIEW"
    )
    with create_engine(os.environ["ARGUS_DATABASE_URL"]).connect() as connection:
        record = PostgresDecisionRepository(connection).get(
            missing.json()["decision"]["decision_id"]
        )
        assert [x.code for x in record.context.risk_signals] == [
            "payments_10m",
            "failed_payments_1h",
        ]
        assert (
            record.rule_set_evaluation.evaluations[1].diagnostic.value
            == "MISSING_SIGNAL"
        )


def test_feature_failure_rolls_back_claim_and_replay_avoids_reader(api, monkeypatch):
    http, projection = api
    projection.begin_rebuild()
    prefix = str(uuid4())
    body = payload(prefix)
    key = str(uuid4())
    assert post(http, body, key).status_code == 503
    projection.mark_ready()
    first = post(http, body, key)
    assert first.status_code == 200 and first.json()["replayed"] is False

    def unavailable(**kwargs):
        raise RedisConnectionError("offline")

    monkeypatch.setattr(projection, "features_for", unavailable)
    replay = post(http, body, key)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["decision"] == first.json()["decision"]
    assert (
        post(http, payload(str(uuid4())), str(uuid4())).json()["error"]["code"]
        == "FEATURES_UNAVAILABLE"
    )
    assert post(http, payload(prefix, amount=101), key).status_code == 409


def test_concurrent_same_key_creates_one_decision(api):
    _, projection = api
    projection.begin_rebuild()
    projection.mark_ready()
    prefix = str(uuid4())
    key = str(uuid4())
    facts = PaymentDecisionInput.model_validate(payload(prefix)["facts"])
    engine = create_engine(os.environ["ARGUS_DATABASE_URL"])
    service = DecisionService(engine, projection)
    barrier = Barrier(2)

    def decide():
        barrier.wait(timeout=5)
        return service.decide(facts, key)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: decide(), range(2)))
        assert sorted(x.replayed for x in results) == [False, True]
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    select(func.count())
                    .select_from(s.decisions)
                    .where(s.decisions.c.subject_id == f"{prefix}-transaction")
                )
                == 1
            )
    finally:
        engine.dispose()
