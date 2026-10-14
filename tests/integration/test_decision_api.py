"""Decision API behavior against a real, migrated PostgreSQL database."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from argus.apps.decision_api.main import app
from argus.apps.decision_api.service import DecisionService
from argus.domain.models import DecisionContext
from argus.persistence import schema as s
from argus.persistence.database import create_engine
from argus.persistence.repository import PostgresDecisionRepository

TIME = "2026-01-02T00:00:00Z"


def payload(prefix: str, counts=(0, 0, 0), amount=100):
    return {
        "context": {
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
            "devices": [],
            "risk_signals": [
                {"code": code, "value": value, "observed_at": TIME, "source": "caller"}
                for code, value in zip(
                    ("payments_10m", "accounts_on_device", "failed_payments_1h"),
                    counts,
                    strict=True,
                )
            ],
        }
    }


def post(client, body, key):
    return client.post(
        "/v1/decisions/payment", json=body, headers={"Idempotency-Key": key}
    )


def test_persistence_replay_and_conflicts():
    prefix = str(uuid4())
    body = payload(prefix)
    key = str(uuid4())
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        first = post(client, body, key)
        assert first.status_code == 200, first.text
        assert first.json()["replayed"] is False
        assert first.json()["decision"]["action"] == "ALLOW"
        replay = post(client, body, key)
        assert replay.status_code == 200, replay.text
        assert replay.json()["replayed"] is True
        assert replay.json()["decision"] == first.json()["decision"]
        changed = payload(prefix, counts=(5, 0, 0))
        conflict = post(client, changed, key)
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

        # Fact conflict after claim must roll the new key back.
        failed_key = str(uuid4())
        conflict = post(client, payload(prefix, amount=101), failed_key)
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["error"]["code"] == "AUTHORITATIVE_FACT_CONFLICT"
        corrected = post(client, body, failed_key)
        assert corrected.status_code == 200, corrected.text

    engine = create_engine(os.environ["ARGUS_DATABASE_URL"])
    with engine.connect() as connection:
        record = PostgresDecisionRepository(connection).get(
            first.json()["decision"]["decision_id"]
        )
        assert record.decision.model_dump(mode="json") == first.json()["decision"]
        assert (
            connection.scalar(
                select(func.count())
                .select_from(s.decisions)
                .where(s.decisions.c.subject_id == f"{prefix}-transaction")
            )
            == 2
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(s.decision_idempotency)
                .where(s.decision_idempotency.c.idempotency_key == key)
            )
            == 1
        )
    engine.dispose()


def test_validation_and_policy_paths():
    with TestClient(app) as client:
        fixed_id = str(uuid4())
        app.state.service.id_factory = lambda: fixed_id
        app.state.service.clock = lambda: datetime(2026, 1, 2, tzinfo=UTC)
        fixed = post(client, payload(str(uuid4())), str(uuid4()))
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["decision"]["decision_id"] == fixed_id
        assert fixed.json()["decision"]["decided_at"] == TIME
        app.state.service.id_factory = lambda: str(uuid4())
        app.state.service.clock = lambda: datetime.now(UTC)
        for counts, expected in (
            ((0, 0, 0), "ALLOW"),
            ((5, 0, 0), "CHALLENGE"),
            ((0, 3, 0), "REVIEW"),
        ):
            response = post(client, payload(str(uuid4()), counts), str(uuid4()))
            assert response.status_code == 200, response.text
            assert response.json()["decision"]["action"] == expected
            assert response.json()["decision"]["rule_set_version"] == 1
            assert response.json()["decision"]["policy_version"] == 1
        missing = payload(str(uuid4()))
        missing["context"]["risk_signals"] = []
        response = post(client, missing, str(uuid4()))
        assert response.status_code == 200
        assert response.json()["decision"]["action"] == "REVIEW"
        invalid = payload(str(uuid4()))
        invalid["context"]["payment_attempt"]["transaction_id"] = "wrong"
        assert post(client, invalid, str(uuid4())).status_code == 422
        assert client.post("/v1/decisions/payment", json=invalid).status_code == 422
        assert post(client, payload(str(uuid4())), "  ").status_code == 422
        assert post(client, payload(str(uuid4())), "x" * 256).status_code == 422


def test_concurrent_same_key_creates_one_decision():
    prefix = str(uuid4())
    key = str(uuid4())
    context = DecisionContext.model_validate(payload(prefix)["context"])
    engine = create_engine(os.environ["ARGUS_DATABASE_URL"])
    service = DecisionService(engine)
    barrier = Barrier(2)

    def decide():
        barrier.wait(timeout=5)
        return service.decide(context, key)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: decide(), range(2)))
        assert len({result.decision.decision_id for result in results}) == 1
        assert sorted(result.replayed for result in results) == [False, True]
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
