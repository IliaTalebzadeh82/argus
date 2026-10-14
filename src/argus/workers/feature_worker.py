"""At-least-once Kafka consumption and explicit Redis rebuild."""

import os
from uuid import uuid4

from confluent_kafka import Consumer, KafkaException, TopicPartition

from argus.events.features import ApplyResult
from argus.events.kafka import FRAUD_TOPIC, deserialize_fraud_event, fraud_record_key
from argus.features.redis_projection import (
    NAMESPACE,
    ProjectionState,
    RedisFeatureProjector,
    create_redis_client,
)

FEATURE_GROUP_ID = "argus-feature-projection-v1"


def live_consumer(bootstrap_servers: str, group_id: str = FEATURE_GROUP_ID) -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
        }
    )


def checked_event(message: object):
    if message.error() is not None:
        raise KafkaException(message.error())
    try:
        event = deserialize_fraud_event(message.value())
        if message.key() != fraud_record_key(event):
            raise ValueError("Kafka record key does not match payload.user_id")
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"invalid Kafka record {message.topic()}[{message.partition()}]"
            f"@{message.offset()}: {exc}"
        ) from exc
    return event


class FeatureWorker:
    def __init__(self, consumer: Consumer, projector: RedisFeatureProjector) -> None:
        self.consumer = consumer
        self.projector = projector

    def process_message(self, message: object) -> ApplyResult:
        event = checked_event(message)
        result = self.projector.apply(event)
        if result not in (ApplyResult.APPLIED, ApplyResult.DUPLICATE):
            raise RuntimeError(f"unexpected Redis apply result: {result}")
        committed = self.consumer.commit(
            offsets=[
                TopicPartition(
                    message.topic(), message.partition(), message.offset() + 1
                )
            ],
            asynchronous=False,
        )
        if not committed or len(committed) != 1 or committed[0].error is not None:
            raise RuntimeError(f"Kafka offset commit failed: {committed}")
        if committed[0].offset != message.offset() + 1:
            raise RuntimeError(f"Kafka committed unexpected offset: {committed}")
        return result

    def process_one(self, timeout: float = 1.0) -> ApplyResult | None:
        message = self.consumer.poll(timeout)
        if message is None:
            return None
        return self.process_message(message)


def rebuild_from_kafka(
    bootstrap_servers: str, topic: str, projector: RedisFeatureProjector
) -> int:
    state = projector.state()
    if state == ProjectionState.READY:
        return 0
    if state == ProjectionState.UNINITIALIZED:
        projector.begin_rebuild()
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": f"argus-feature-rebuild-{uuid4()}",
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
        }
    )
    try:
        metadata = consumer.list_topics(topic=topic, timeout=15)
        topic_metadata = metadata.topics.get(topic)
        if topic_metadata is None or topic_metadata.error is not None:
            raise RuntimeError(f"rebuild topic unavailable: {topic}")
        targets: dict[int, int] = {}
        assignments = []
        for partition in sorted(topic_metadata.partitions):
            tp = TopicPartition(topic, partition)
            low, high = consumer.get_watermark_offsets(tp, timeout=15, cached=False)
            if low != 0:
                raise RuntimeError(
                    f"cannot rebuild exact history: {topic}[{partition}] low={low}"
                )
            targets[partition] = high
            if high > low:
                assignments.append(TopicPartition(topic, partition, low))
        consumer.assign(assignments)
        next_offsets = {partition: 0 for partition in targets}
        count = 0
        while any(next_offsets[p] < high for p, high in targets.items()):
            message = consumer.poll(10)
            if message is None:
                raise TimeoutError("Kafka rebuild stalled before captured cutoff")
            if message.error() is not None:
                raise KafkaException(message.error())
            partition = message.partition()
            if message.offset() >= targets[partition]:
                consumer.pause([TopicPartition(topic, partition)])
                continue
            if message.offset() != next_offsets[partition]:
                missing = next_offsets[partition]
                raise RuntimeError(
                    f"Kafka history gap at {topic}[{partition}]@{missing}"
                )
            projector.apply(checked_event(message))
            count += 1
            next_offsets[partition] = message.offset() + 1
            if next_offsets[partition] == targets[partition]:
                consumer.pause([TopicPartition(topic, partition)])
        projector.mark_ready()
        return count
    finally:
        consumer.close()


def main() -> None:
    bootstrap = os.environ["ARGUS_KAFKA_BOOTSTRAP_SERVERS"]
    redis_url = os.environ["ARGUS_REDIS_URL"]
    topic = os.environ.get("ARGUS_FRAUD_TOPIC", FRAUD_TOPIC)
    group_id = os.environ.get("ARGUS_FEATURE_GROUP_ID", FEATURE_GROUP_ID)
    namespace = os.environ.get("ARGUS_FEATURE_NAMESPACE", NAMESPACE)
    client = create_redis_client(redis_url)
    try:
        projector = RedisFeatureProjector(client, namespace=namespace)
        rebuild_from_kafka(bootstrap, topic, projector)
        consumer = live_consumer(bootstrap, group_id)
        try:
            consumer.subscribe([topic])
            worker = FeatureWorker(consumer, projector)
            while True:
                worker.process_one()
        finally:
            consumer.close()
    finally:
        client.close()


if __name__ == "__main__":
    main()
