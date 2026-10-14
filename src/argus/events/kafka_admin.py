"""Explicit provisioning and verification of the Phase-2 fraud topic."""

import os

from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient, ConfigResource, NewTopic

from argus.events.kafka import FRAUD_TOPIC

PARTITIONS = 3
RETENTION_MS = "-1"


def ensure_fraud_topic(bootstrap_servers: str, *, topic: str = FRAUD_TOPIC) -> None:
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    metadata = admin.list_topics(timeout=15)
    existing = metadata.topics.get(topic)
    if existing is None:
        admin.create_topics(
            [
                NewTopic(
                    topic,
                    num_partitions=PARTITIONS,
                    replication_factor=1,
                    config={
                        "retention.ms": RETENTION_MS,
                        "retention.bytes": "-1",
                        "cleanup.policy": "delete",
                    },
                )
            ]
        )[topic].result(timeout=30)
    elif existing.error is not None:
        raise KafkaException(existing.error)
    metadata = admin.list_topics(topic=topic, timeout=15)
    current = metadata.topics[topic]
    if current.error is not None:
        raise KafkaException(current.error)
    if len(current.partitions) != PARTITIONS:
        raise ValueError(f"{topic}: expected {PARTITIONS} partitions")
    for partition in current.partitions.values():
        if len(partition.replicas) != 1:
            raise ValueError(f"{topic}: expected local replication factor 1")
    resource = ConfigResource("topic", topic)
    configs = admin.describe_configs([resource])[resource].result(timeout=15)
    if configs["retention.ms"].value != RETENTION_MS:
        raise ValueError(f"{topic}: expected retention.ms={RETENTION_MS}")
    if configs["retention.bytes"].value != "-1":
        raise ValueError(f"{topic}: expected retention.bytes=-1")
    if configs["cleanup.policy"].value != "delete":
        raise ValueError(f"{topic}: expected cleanup.policy=delete")


if __name__ == "__main__":
    ensure_fraud_topic(
        os.environ["ARGUS_KAFKA_BOOTSTRAP_SERVERS"],
        topic=os.environ.get("ARGUS_FRAUD_TOPIC", FRAUD_TOPIC),
    )
