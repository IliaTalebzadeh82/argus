"""Measured CP05 transport, freshness, rebalance, and poison behavior."""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from confluent_kafka import TopicPartition
from confluent_kafka.admin import AdminClient
from fastapi.testclient import TestClient

from argus.apps.decision_api.main import app
from argus.events.envelope import EventEnvelope
from argus.events.features import ApplyResult, ReferenceFeatureProjector
from argus.events.fraud import AccountCreatedPayload, PaymentAttemptedPayload
from argus.events.kafka import FRAUD_TOPIC, KafkaFraudEventProducer
from argus.events.kafka_admin import ensure_fraud_topic
from argus.events.kafka_lag import inspect_feature_lag
from argus.features.redis_projection import RedisFeatureProjector, create_redis_client
from argus.workers.feature_worker import FEATURE_GROUP_ID, FeatureWorker, live_consumer

T = datetime(2026, 1, 2, 12, tzinfo=UTC)
BOOTSTRAP = os.environ.get("ARGUS_KAFKA_BOOTSTRAP_SERVERS")
REDIS_URL = os.environ.get("ARGUS_REDIS_URL")


@pytest.fixture
def environment():
    if not BOOTSTRAP or not REDIS_URL or not os.environ.get("ARGUS_DATABASE_URL"):
        pytest.fail("Explicit Kafka, Redis, and database URLs are required")
    topic = f"argus.cp05.test.{uuid4().hex}"
    namespace = f"argus:features:v1:test:{uuid4().hex}:"
    ensure_fraud_topic(BOOTSTRAP, topic=topic)
    client = create_redis_client(REDIS_URL)
    projector = RedisFeatureProjector(client, namespace=namespace)
    projector.begin_rebuild()
    projector.mark_ready()
    try:
        yield topic, projector
    finally:
        keys = list(client.scan_iter(f"{namespace}*"))
        if keys:
            client.delete(*keys)
        client.close()


def event(kind, user, at, number):
    if kind == "account.created":
        payload = AccountCreatedPayload(user_id=user, device_id=f"{user}-device")
        subject = user
    else:
        payload = PaymentAttemptedPayload(
            payment_id=f"{user}-event-payment-{number}",
            transaction_id=f"{user}-event-transaction-{number}",
            user_id=user,
        )
        subject = payload.payment_id
    return EventEnvelope[type(payload)](
        event_id=uuid4(),
        event_type=kind,
        event_version=1,
        occurred_at=at,
        produced_at=datetime.now(UTC),
        producer="cp05",
        trace_id=f"cp05-{number}",
        subject_id=subject,
        payload=payload,
    )


def publish(topic, events):
    producer = KafkaFraudEventProducer(BOOTSTRAP, topic=topic)
    for item in events:
        producer.publish(item)


def consumer(topic, group):
    result = live_consumer(BOOTSTRAP, group)
    result.subscribe([topic])
    return result


def drain(workers, topic, group, timeout=30):
    deadline = time.monotonic() + timeout
    results = []
    while time.monotonic() < deadline:
        for worker in workers:
            value = worker.process_one(0.1)
            if value is not None:
                results.append(value)
        if (
            inspect_feature_lag(
                BOOTSTRAP, topic=topic, group_id=group
            ).total_pending_records
            == 0
        ):
            return results
    raise TimeoutError(f"lag did not drain: {topic} group={group}")


def facts(user):
    stamp = T.isoformat()
    return {
        "facts": {
            "user": {"user_id": user, "created_at": stamp},
            "transaction": {
                "transaction_id": f"{user}-tx",
                "user_id": user,
                "merchant_id": "merchant",
                "amount": {"amount_minor": 100, "currency": "USD"},
                "created_at": stamp,
            },
            "payment_attempt": {
                "payment_id": f"{user}-request-payment",
                "transaction_id": f"{user}-tx",
                "attempted_at": stamp,
            },
            "devices": [{"device_id": f"{user}-device", "first_seen_at": stamp}],
            "observed_device_id": f"{user}-device",
        }
    }


def decide(http, body, key=None):
    result = http.post(
        "/v1/decisions/payment",
        json=body,
        headers={"Idempotency-Key": key or str(uuid4())},
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_lag_grows_and_returns_to_zero(environment):
    topic, projector = environment
    group = f"cp05-{uuid4().hex}"
    before = inspect_feature_lag(BOOTSTRAP, topic=topic, group_id=group)
    assert all(p.committed_offset is None for p in before.partitions)
    assert before.total_pending_records == 0
    events = [event("payment.attempted", "lag-user", T, i) for i in range(6)]
    publish(topic, events)
    pending = inspect_feature_lag(BOOTSTRAP, topic=topic, group_id=group)
    assert pending.total_pending_records == 6
    c = consumer(topic, group)
    try:
        start = time.monotonic()
        assert len(drain([FeatureWorker(c, projector)], topic, group)) == 6
        elapsed = time.monotonic() - start
        final = inspect_feature_lag(BOOTSTRAP, topic=topic, group_id=group)
        assert final.total_pending_records == 0
        print(
            json.dumps(
                {
                    "lag_test_pending": pending.total_pending_records,
                    "lag_test_elapsed_seconds": round(elapsed, 3),
                }
            )
        )
    finally:
        c.close()


def test_stale_ready_catchup_replay_and_zero_lag_late_event(environment, monkeypatch):
    _, projector = environment
    topic = FRAUD_TOPIC
    # The live topic/group are exercised with an isolated Redis namespace.
    group = FEATURE_GROUP_ID
    user = f"cp05-{uuid4().hex}"
    baseline = event("account.created", user, T - timedelta(minutes=2), 0)
    reference = ReferenceFeatureProjector()
    reference.apply(baseline)
    publish(topic, [baseline])
    c = consumer(topic, group)
    try:
        drain([FeatureWorker(c, projector)], topic, group)
    finally:
        c.close()
    assert (
        inspect_feature_lag(
            BOOTSTRAP, topic=topic, group_id=group
        ).total_pending_records
        == 0
    )
    monkeypatch.setenv("ARGUS_FEATURE_NAMESPACE", projector.namespace)
    with TestClient(app) as http:
        body = facts(user)
        assert http.get("/health/ready").status_code == 200
        baseline_result = decide(http, body)
        assert baseline_result["decision"]["action"] == "ALLOW"
        backlog = [
            event("payment.attempted", user, T - timedelta(minutes=1), i)
            for i in range(30)
        ]
        publish(topic, backlog)
        for item in backlog:
            reference.apply(item)
        lag = inspect_feature_lag(BOOTSTRAP, topic=topic, group_id=group)
        assert lag.total_pending_records == 30
        redis_stale = projector.features_for(
            user_id=user, device_id=f"{user}-device", as_of=T
        )
        truth = reference.features_for(
            user_id=user, device_id=f"{user}-device", as_of=T
        )
        assert (redis_stale.payments_10m, truth.payments_10m) == (0, 30)
        ready_during_lag = http.get("/health/ready").status_code
        assert ready_during_lag == 200
        stale_key = str(uuid4())
        stale = decide(http, body, stale_key)
        assert stale["decision"]["action"] == "ALLOW"
        c = consumer(topic, group)
        try:
            start = time.monotonic()
            drain([FeatureWorker(c, projector)], topic, group)
            elapsed = time.monotonic() - start
        finally:
            c.close()
        assert (
            inspect_feature_lag(
                BOOTSTRAP, topic=topic, group_id=group
            ).total_pending_records
            == 0
        )
        assert (
            projector.features_for(user_id=user, device_id=f"{user}-device", as_of=T)
            == truth
        )
        current = decide(http, body)
        assert current["decision"]["action"] == "CHALLENGE"
        replay = decide(http, body, stale_key)
        assert replay["replayed"] and replay["decision"] == stale["decision"]
        print(
            json.dumps(
                {
                    "baseline_lag": 0,
                    "backlog": lag.total_pending_records,
                    "stale_redis_payments": redis_stale.payments_10m,
                    "stale_reference_payments": truth.payments_10m,
                    "readiness_during_lag": ready_during_lag,
                    "stale_action": stale["decision"]["action"],
                    "catchup_seconds": round(elapsed, 3),
                    "after_action": current["decision"]["action"],
                    "replay_action": replay["decision"]["action"],
                }
            )
        )
        # A later arrival has earlier event time, despite initial zero lag.
        late_user = f"cp05-late-{uuid4().hex}"
        late_body = facts(late_user)
        before = decide(http, late_body)
        assert before["decision"]["action"] == "ALLOW"
        late = [
            event("payment.attempted", late_user, T - timedelta(seconds=1), i)
            for i in range(5)
        ]
        publish(topic, late)
        c = consumer(topic, group)
        try:
            drain([FeatureWorker(c, projector)], topic, group)
        finally:
            c.close()
        assert (
            inspect_feature_lag(
                BOOTSTRAP, topic=topic, group_id=group
            ).total_pending_records
            == 0
        )
        late_reference = ReferenceFeatureProjector()
        for item in late:
            late_reference.apply(item)
        after_value = projector.features_for(
            user_id=late_user, device_id=f"{late_user}-device", as_of=T
        )
        assert after_value == late_reference.features_for(
            user_id=late_user, device_id=f"{late_user}-device", as_of=T
        )
        after = decide(http, late_body)
        assert after["decision"]["action"] == "CHALLENGE"
        print(
            json.dumps(
                {
                    "late_lag_before": 0,
                    "late_lag_after": 0,
                    "late_payments_before": 0,
                    "late_payments_after": after_value.payments_10m,
                    "late_action_before": before["decision"]["action"],
                    "late_action_after": after["decision"]["action"],
                }
            )
        )


def group_state(group):
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    description = admin.describe_consumer_groups([group], request_timeout=3)[
        group
    ].result(timeout=5)
    return [
        sorted((tp.topic, tp.partition) for tp in member.assignment.topic_partitions)
        for member in description.members
    ]


def wait_assignments(group, consumers, count, timeout=45, worker=None):
    deadline = time.monotonic() + timeout
    processed = []
    while time.monotonic() < deadline:
        for c in consumers:
            message = c.poll(0.1)
            if message is not None:
                if worker is None:
                    raise AssertionError("unexpected record during assignment wait")
                processed.append(worker.process_message(message))
        try:
            assignments = group_state(group)
        except TimeoutError:
            continue  # Coordinator can be temporarily unavailable during join.
        if len(assignments) == count and sum(map(len, assignments)) == 3:
            return assignments, processed
    raise TimeoutError(f"group did not stabilize: group={group}, expected={count}")


def test_two_workers_rebalance_duplicates_and_out_of_order(environment):
    topic, projector = environment
    group = f"cp05-{uuid4().hex}"
    users = [f"rebalance-{uuid4().hex}" for _ in range(12)]
    unique = [
        event("payment.attempted", user, T - timedelta(minutes=i % 4), i)
        for i, user in enumerate(users)
    ]
    # Repeated event IDs and delivery order distinct from occurred_at order.
    delivery = unique + [unique[1], unique[4], unique[1], unique[0]]
    reference = ReferenceFeatureProjector()
    for item in unique:
        reference.apply(item)
    c1, c2 = consumer(topic, group), consumer(topic, group)
    try:
        before, _ = wait_assignments(group, [c1, c2], 2)
        assert all(before) and not set(before[0]).intersection(before[1])
        assert len(set(before[0] + before[1])) == 3
        publish(topic, delivery)
        initial_lag = inspect_feature_lag(
            BOOTSTRAP, topic=topic, group_id=group
        ).total_pending_records
        assert initial_lag == len(delivery)
        worker1, worker2 = FeatureWorker(c1, projector), FeatureWorker(c2, projector)
        # Both members commit live work before one leaves.
        for worker in (worker1, worker2):
            deadline = time.monotonic() + 15
            value = None
            while value is None and time.monotonic() < deadline:
                value = worker.process_one(0.1)
            assert value == ApplyResult.APPLIED
        # Apply before rebalance without committing: explicit duplicate window.
        first = None
        deadline = time.monotonic() + 15
        while first is None and time.monotonic() < deadline:
            first = c1.poll(0.1)
        assert first is not None
        from argus.workers.feature_worker import checked_event

        assert projector.apply(checked_event(first)) == ApplyResult.APPLIED
        c1.close()
        after, during_rebalance = wait_assignments(group, [c2], 1, worker=worker2)
        assert len(after[0]) == 3
        pending = inspect_feature_lag(
            BOOTSTRAP, topic=topic, group_id=group
        ).total_pending_records
        results = during_rebalance + drain([worker2], topic, group)
        assert ApplyResult.DUPLICATE in results
        assert len(results) == len(delivery) - 2
        for user in users:
            for at in (T, T - timedelta(minutes=2)):
                assert projector.features_for(
                    user_id=user, device_id=None, as_of=at
                ) == reference.features_for(user_id=user, device_id=None, as_of=at)
        print(
            json.dumps(
                {
                    "members_before": 2,
                    "assignments_before": before,
                    "members_after": 1,
                    "assignments_after": after,
                    "initial_lag": initial_lag,
                    "lag_before_drain": pending,
                    "lag_after_drain": 0,
                    "deliveries": len(delivery),
                    "logical_events": len(unique),
                    "duplicate_results": results.count(ApplyResult.DUPLICATE),
                    "committed_by_both_before_loss": 2,
                }
            )
        )
    finally:
        c2.close()


def test_poison_blocks_partition_after_restart(environment):
    topic, projector = environment
    group = f"cp05-{uuid4().hex}"
    user = f"poison-{uuid4().hex}"
    valid_a = event("payment.attempted", user, T, 1)
    valid_b = event("payment.attempted", user, T, 2)
    producer = KafkaFraudEventProducer(BOOTSTRAP, topic=topic)
    producer.publish(valid_a)
    # Same key guarantees same partition; malformed bytes remain a poison record.
    producer.client.produce(topic, key=user.encode(), value=b"not-json")
    assert producer.client.flush(30) == 0
    producer.publish(valid_b)
    c = consumer(topic, group)
    try:
        worker = FeatureWorker(c, projector)
        deadline = time.monotonic() + 15
        a = None
        while a is None and time.monotonic() < deadline:
            a = c.poll(0.1)
        assert a is not None
        assert worker.process_message(a) == ApplyResult.APPLIED
        poison = c.poll(5)
        assert poison is not None and poison.partition() == a.partition()
        with pytest.raises(ValueError, match="invalid Kafka record"):
            worker.process_message(poison)
        committed = c.committed([TopicPartition(topic, a.partition())], timeout=10)[
            0
        ].offset
        assert committed == poison.offset()
    finally:
        c.close()
    c = consumer(topic, group)
    try:
        deadline = time.monotonic() + 15
        again = None
        while again is None and time.monotonic() < deadline:
            again = c.poll(0.1)
        assert again is not None and again.offset() == poison.offset()
        with pytest.raises(ValueError, match="invalid Kafka record"):
            FeatureWorker(c, projector).process_message(again)
        assert (
            inspect_feature_lag(
                BOOTSTRAP, topic=topic, group_id=group
            ).total_pending_records
            == 2
        )
        assert (
            projector.features_for(user_id=user, device_id=None, as_of=T).payments_10m
            == 1
        )
        print(
            json.dumps(
                {
                    "poison_partition": poison.partition(),
                    "poison_offset": poison.offset(),
                    "committed_offset": committed,
                    "redelivered_offset": again.offset(),
                    "pending_with_valid_b_blocked": 2,
                }
            )
        )
    finally:
        c.close()
