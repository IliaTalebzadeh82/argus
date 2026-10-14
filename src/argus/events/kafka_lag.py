"""Operator-facing Kafka transport backlog snapshot; never a decision signal."""

import json
import os
from dataclasses import asdict, dataclass

from confluent_kafka import OFFSET_INVALID, ConsumerGroupTopicPartitions, TopicPartition
from confluent_kafka.admin import (
    AdminClient,
    OffsetSpec,
)

from argus.events.kafka import FRAUD_TOPIC
from argus.workers.feature_worker import FEATURE_GROUP_ID


@dataclass(frozen=True)
class PartitionLag:
    partition: int
    low_offset: int
    high_offset: int
    committed_offset: int | None
    pending_records: int

    @classmethod
    def from_offsets(
        cls, partition: int, low: int, high: int, committed: int | None
    ) -> "PartitionLag":
        if (
            low < 0
            or high < low
            or (committed is not None and not low <= committed <= high)
        ):
            raise ValueError(
                f"invalid offsets for partition {partition}: low={low}, high={high}, "
                f"committed={committed}"
            )
        # The live group starts at earliest. No commit remains distinguishable
        # from a real checkpoint at the retained low offset.
        return cls(
            partition,
            low,
            high,
            committed,
            high - (low if committed is None else committed),
        )


@dataclass(frozen=True)
class FeatureLagSnapshot:
    topic: str
    group_id: str
    partitions: tuple[PartitionLag, ...]
    total_pending_records: int


def inspect_feature_lag(
    bootstrap_servers: str,
    *,
    topic: str = FRAUD_TOPIC,
    group_id: str = FEATURE_GROUP_ID,
) -> FeatureLagSnapshot:
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata = admin.list_topics(topic=topic, timeout=15)
    topic_metadata = metadata.topics.get(topic)
    if topic_metadata is None or topic_metadata.error is not None:
        raise RuntimeError(f"Kafka topic unavailable: {topic}")
    partitions = sorted(topic_metadata.partitions)
    keys = [TopicPartition(topic, partition) for partition in partitions]
    low_futures = admin.list_offsets(
        {key: OffsetSpec.earliest() for key in keys}, request_timeout=15
    )
    high_futures = admin.list_offsets(
        {key: OffsetSpec.latest() for key in keys}, request_timeout=15
    )
    group_result = admin.list_consumer_group_offsets(
        [ConsumerGroupTopicPartitions(group_id, keys)], request_timeout=15
    )[group_id].result(timeout=20)
    committed = {
        position.partition: position for position in group_result.topic_partitions
    }
    results = []
    for key in keys:
        low = low_futures[key].result(timeout=20).offset
        high = high_futures[key].result(timeout=20).offset
        position = committed.get(key.partition)
        if position is not None and position.error is not None:
            raise RuntimeError(f"Kafka group offset error: {position.error}")
        offset = (
            None
            if position is None or position.offset == OFFSET_INVALID
            else position.offset
        )
        results.append(PartitionLag.from_offsets(key.partition, low, high, offset))
    return FeatureLagSnapshot(
        topic, group_id, tuple(results), sum(item.pending_records for item in results)
    )


def main() -> None:
    snapshot = inspect_feature_lag(
        os.environ["ARGUS_KAFKA_BOOTSTRAP_SERVERS"],
        topic=os.environ.get("ARGUS_FRAUD_TOPIC", FRAUD_TOPIC),
        group_id=os.environ.get("ARGUS_FEATURE_GROUP_ID", FEATURE_GROUP_ID),
    )
    print(json.dumps(asdict(snapshot), sort_keys=True))


if __name__ == "__main__":
    main()
