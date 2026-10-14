"""Real Kafka and Redis checks for transport, offsets, and replay."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from confluent_kafka import Consumer, TopicPartition
from redis.exceptions import ConnectionError as RedisConnectionError

from argus.events.envelope import EventEnvelope
from argus.events.features import ApplyResult, ReferenceFeatureProjector
from argus.events.fraud import (
    AccountCreatedPayload,
    ChargebackReceivedPayload,
    PaymentAttemptedPayload,
    PaymentFailedPayload,
    TransactionCompletedPayload,
)
from argus.events.kafka import (
    KafkaFraudEventProducer,
    deserialize_fraud_event,
    fraud_record_key,
    serialize_fraud_event,
)
from argus.events.kafka_admin import ensure_fraud_topic
from argus.features.redis_projection import (
    ProjectionState,
    RedisFeatureProjector,
    create_redis_client,
)
from argus.workers.feature_worker import (
    FeatureWorker,
    live_consumer,
    rebuild_from_kafka,
)

T = datetime(2026, 10, 14, 12, tzinfo=UTC)


@pytest.fixture
def environment():
    bootstrap = os.environ.get("ARGUS_KAFKA_BOOTSTRAP_SERVERS")
    redis_url = os.environ.get("ARGUS_REDIS_URL")
    if not bootstrap or not redis_url:
        pytest.fail("ARGUS_KAFKA_BOOTSTRAP_SERVERS and ARGUS_REDIS_URL are required")
    topic = f"argus.cp03.test.{uuid4().hex}"
    namespace = f"argus:features:v1:test:{uuid4().hex}:"
    ensure_fraud_topic(bootstrap, topic=topic)
    client = create_redis_client(redis_url)
    projector = RedisFeatureProjector(client, namespace=namespace)
    try:
        yield bootstrap, topic, projector
    finally:
        keys = list(client.scan_iter(f"{namespace}*"))
        if keys:
            client.delete(*keys)
        client.close()


def event(number: int, kind: str, payload: object, at: datetime = T):
    subject = {
        "account.created": "user_id",
        "payment.attempted": "payment_id",
        "payment.failed": "payment_id",
        "transaction.completed": "transaction_id",
        "chargeback.received": "chargeback_id",
    }[kind]
    return EventEnvelope[type(payload)](
        event_id=uuid4(),
        event_type=kind,
        event_version=1,
        occurred_at=at,
        produced_at=T,
        producer="test",
        trace_id=f"trace-{number}",
        subject_id=getattr(payload, subject),
        payload=payload,
    )


def history():
    return [
        event(1, "account.created", AccountCreatedPayload(user_id="a", device_id="d")),
        event(
            2,
            "account.created",
            AccountCreatedPayload(user_id="b", device_id="d"),
            T - timedelta(hours=2),
        ),
        event(
            3,
            "payment.attempted",
            PaymentAttemptedPayload(payment_id="p", transaction_id="t", user_id="a"),
        ),
        event(
            4,
            "payment.failed",
            PaymentFailedPayload(payment_id="p", transaction_id="t", user_id="a"),
        ),
        event(
            5,
            "transaction.completed",
            TransactionCompletedPayload(transaction_id="t", user_id="a"),
        ),
        event(
            6,
            "chargeback.received",
            ChargebackReceivedPayload(
                chargeback_id="c", transaction_id="t", user_id="a"
            ),
        ),
    ]


def publish_all(bootstrap: str, topic: str, events: list) -> None:
    producer = KafkaFraudEventProducer(bootstrap, topic=topic)
    for item in events:
        producer.publish(item)


def consumer_for(bootstrap: str, topic: str, group: str) -> Consumer:
    consumer = live_consumer(bootstrap, group)
    consumer.subscribe([topic])
    return consumer


def receive(consumer: Consumer):
    for _ in range(20):
        message = consumer.poll(1)
        if message is not None:
            return message
    raise TimeoutError("test Kafka message not delivered")


def committed(consumer: Consumer, message: object) -> int:
    return consumer.committed(
        [TopicPartition(message.topic(), message.partition())], timeout=10
    )[0].offset


def assert_reference(projector: RedisFeatureProjector, events: list) -> None:
    reference = ReferenceFeatureProjector()
    for item in events:
        reference.apply(item)
    for user in ("a", "b"):
        for device in ("d", None):
            assert projector.features_for(
                user_id=user, device_id=device, as_of=T
            ) == reference.features_for(user_id=user, device_id=device, as_of=T)


def test_topic_provisioning(environment) -> None:
    bootstrap, topic, _ = environment
    ensure_fraud_topic(bootstrap, topic=topic)
    # Existing 3-partition topic with incompatible retention is rejected.
    from confluent_kafka.admin import (
        AdminClient,
        AlterConfigOpType,
        ConfigEntry,
        ConfigResource,
    )

    admin = AdminClient({"bootstrap.servers": bootstrap})
    resource = ConfigResource("topic", topic)
    resource.add_incremental_config(
        ConfigEntry(
            "retention.ms", "60000", incremental_operation=AlterConfigOpType.SET
        )
    )
    admin.incremental_alter_configs([resource])[resource].result(timeout=15)
    with pytest.raises(ValueError, match="retention.ms"):
        ensure_fraud_topic(bootstrap, topic=topic)


def test_live_history_duplicate_and_group_offsets(environment) -> None:
    bootstrap, topic, projector = environment
    events = history()
    publish_all(bootstrap, topic, events + [events[2]])
    projector.begin_rebuild()
    projector.mark_ready()
    group = f"test-{uuid4()}"
    consumer = consumer_for(bootstrap, topic, group)
    try:
        worker = FeatureWorker(consumer, projector)
        results = []
        for _ in range(7):
            message = receive(consumer)
            assert message.key() == fraud_record_key(
                deserialize_fraud_event(message.value())
            )
            results.append(worker.process_message(message))
        assert results.count(ApplyResult.APPLIED) == 6
        assert results.count(ApplyResult.DUPLICATE) == 1
        assert_reference(projector, events)
        positions = consumer.committed(
            [TopicPartition(topic, partition) for partition in range(3)], timeout=10
        )
        assert (
            sum(position.offset for position in positions if position.offset >= 0) == 7
        )
    finally:
        consumer.close()
    resumed = consumer_for(bootstrap, topic, group)
    try:
        assert resumed.poll(2) is None
    finally:
        resumed.close()


def test_apply_before_commit_redelivers(environment) -> None:
    bootstrap, topic, projector = environment
    item = history()[2]
    publish_all(bootstrap, topic, [item])
    projector.begin_rebuild()
    projector.mark_ready()
    group = f"test-{uuid4()}"
    consumer = consumer_for(bootstrap, topic, group)
    message = receive(consumer)
    assert projector.apply(item) == ApplyResult.APPLIED
    assert committed(consumer, message) < 0
    consumer.close()
    consumer = consumer_for(bootstrap, topic, group)
    try:
        replay = receive(consumer)
        assert replay.offset() == message.offset()
        assert (
            FeatureWorker(consumer, projector).process_message(replay)
            == ApplyResult.DUPLICATE
        )
        assert committed(consumer, replay) == replay.offset() + 1
        assert_reference(projector, [item])
    finally:
        consumer.close()


def test_unknown_redis_outcome_redelivers(environment) -> None:
    bootstrap, topic, projector = environment
    item = history()[2]
    publish_all(bootstrap, topic, [item])
    projector.begin_rebuild()
    projector.mark_ready()
    group = f"test-{uuid4()}"

    class LostReply:
        def apply(self, value):
            assert projector.apply(value) == ApplyResult.APPLIED
            raise RedisConnectionError("reply lost after Redis applied event")

    consumer = consumer_for(bootstrap, topic, group)
    message = receive(consumer)
    with pytest.raises(RedisConnectionError):
        FeatureWorker(consumer, LostReply()).process_message(message)
    assert committed(consumer, message) < 0
    consumer.close()
    consumer = consumer_for(bootstrap, topic, group)
    try:
        replay = receive(consumer)
        assert (
            FeatureWorker(consumer, projector).process_message(replay)
            == ApplyResult.DUPLICATE
        )
        assert committed(consumer, replay) == replay.offset() + 1
        assert_reference(projector, [item])
    finally:
        consumer.close()


def test_rebuild_partial_recovery_and_ignores_live_offsets(environment) -> None:
    bootstrap, topic, projector = environment
    events = history()
    publish_all(bootstrap, topic, events)
    assert projector.state() == ProjectionState.UNINITIALIZED

    class FailAfterFirst:
        def __init__(self):
            self.count = 0

        def state(self):
            return projector.state()

        def begin_rebuild(self):
            projector.begin_rebuild()

        def apply(self, value):
            result = projector.apply(value)
            self.count += 1
            if self.count == 1:
                raise RedisConnectionError("rebuild interrupted")
            return result

    with pytest.raises(RedisConnectionError):
        rebuild_from_kafka(bootstrap, topic, FailAfterFirst())
    assert projector.state() == ProjectionState.REBUILDING
    assert rebuild_from_kafka(bootstrap, topic, projector) == len(events)
    assert projector.state() == ProjectionState.READY
    assert_reference(projector, events)

    group = f"test-{uuid4()}"
    live = consumer_for(bootstrap, topic, group)
    try:
        worker = FeatureWorker(live, projector)
        for _ in events:
            assert worker.process_message(receive(live)) == ApplyResult.DUPLICATE
    finally:
        live.close()
    fresh = RedisFeatureProjector(
        projector.client, namespace=f"argus:features:v1:test:{uuid4().hex}:"
    )
    try:
        assert rebuild_from_kafka(bootstrap, topic, fresh) == len(events)
        assert_reference(fresh, events)
    finally:
        keys = list(fresh.client.scan_iter(f"{fresh.namespace}*"))
        if keys:
            fresh.client.delete(*keys)


def test_empty_rebuild(environment) -> None:
    bootstrap, topic, projector = environment
    assert rebuild_from_kafka(bootstrap, topic, projector) == 0
    assert projector.state() == ProjectionState.READY
    assert projector.features_for(user_id="a", device_id="d", as_of=T).payments_10m == 0


@pytest.mark.parametrize("poison", ["key", "json", "version"])
def test_poison_blocks_offset(environment, poison: str) -> None:
    bootstrap, topic, projector = environment
    item = history()[2]
    from confluent_kafka import Producer

    raw = Producer({"bootstrap.servers": bootstrap})
    key = b"wrong" if poison == "key" else b"a"
    value = serialize_fraud_event(item)
    if poison == "json":
        value = b"{"
    elif poison == "version":
        value = value.replace(b'"event_version":1', b'"event_version":2')
    raw.produce(topic, key=key, value=value)
    assert raw.flush(10) == 0
    projector.begin_rebuild()
    projector.mark_ready()
    consumer = consumer_for(bootstrap, topic, f"test-{uuid4()}")
    try:
        message = receive(consumer)
        with pytest.raises(ValueError, match="invalid Kafka record"):
            FeatureWorker(consumer, projector).process_message(message)
        assert committed(consumer, message) < 0
    finally:
        consumer.close()


def test_redis_failure_and_commit_failure_do_not_undo(environment) -> None:
    bootstrap, topic, projector = environment
    item = history()[2]
    publish_all(bootstrap, topic, [item])
    projector.begin_rebuild()
    projector.mark_ready()
    consumer = consumer_for(bootstrap, topic, f"test-{uuid4()}")

    class FailingProjector:
        def apply(self, value):
            raise RedisConnectionError("before apply")

    try:
        message = receive(consumer)
        with pytest.raises(RedisConnectionError):
            FeatureWorker(consumer, FailingProjector()).process_message(message)
        assert committed(consumer, message) < 0
        assert projector.apply(item) == ApplyResult.APPLIED

        class FailingCommit:
            def commit(self, **kwargs):
                raise RuntimeError("commit failed")

        with pytest.raises(RuntimeError, match="commit failed"):
            FeatureWorker(FailingCommit(), projector).process_message(message)
        assert committed(consumer, message) < 0
        assert projector.apply(item) == ApplyResult.DUPLICATE
    finally:
        consumer.close()


def test_identity_conflict_does_not_commit(environment) -> None:
    bootstrap, topic, projector = environment
    item = history()[2]
    changed = item.model_copy(
        update={
            "payload": PaymentAttemptedPayload(
                payment_id="different", transaction_id="t", user_id="a"
            ),
            "subject_id": "different",
        }
    )
    publish_all(bootstrap, topic, [item, changed])
    projector.begin_rebuild()
    projector.mark_ready()
    consumer = consumer_for(bootstrap, topic, f"test-{uuid4()}")
    try:
        worker = FeatureWorker(consumer, projector)
        first = receive(consumer)
        assert worker.process_message(first) == ApplyResult.APPLIED
        second = receive(consumer)
        from argus.events.features import EventIdentityConflict

        with pytest.raises(EventIdentityConflict):
            worker.process_message(second)
        assert committed(consumer, second) == second.offset()
    finally:
        consumer.close()
