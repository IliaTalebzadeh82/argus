"""CP05 real Kafka delivery and Redis rebuild against canonical truth."""

import os
from collections import Counter
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from confluent_kafka import Consumer, TopicPartition

from argus.events.features import ApplyResult, ReferenceFeatureProjector
from argus.events.kafka import (
    KafkaFraudEventProducer,
    deserialize_fraud_event,
    fraud_record_key,
)
from argus.events.kafka_admin import PARTITIONS, ensure_fraud_topic
from argus.features.redis_projection import (
    ProjectionState,
    RedisFeatureProjector,
    create_redis_client,
)
from argus.simulation.playback import play_workload
from argus.simulation.spec import WorkloadSpec
from argus.simulation.workload import run_mixed_workload
from argus.workers.feature_worker import rebuild_from_kafka


def test_mixed_workload_kafka_redis_convergence():
    bootstrap = os.environ.get("ARGUS_KAFKA_BOOTSTRAP_SERVERS")
    redis_url = os.environ.get("ARGUS_REDIS_URL")
    if not bootstrap or not redis_url:
        pytest.fail("ARGUS_KAFKA_BOOTSTRAP_SERVERS and ARGUS_REDIS_URL are required")
    spec = WorkloadSpec.from_json(
        Path("configs/simulation/phase-03-demo.json").read_text()
    )
    result = run_mixed_workload(spec.simulation, spec.world, spec.traffic)
    topic = f"argus.cp05.test.{uuid4().hex}"
    namespace = f"argus:features:v1:cp05:{uuid4().hex}:"
    ensure_fraud_topic(bootstrap, topic=topic)
    client = create_redis_client(redis_url)
    projector = RedisFeatureProjector(client, namespace=namespace)
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": f"cp05-{uuid4()}",
            "enable.auto.commit": False,
        }
    )
    try:
        report = play_workload(result, KafkaFraudEventProducer(bootstrap, topic=topic))
        assert report.published_deliveries == result.traffic_summary.delivery_count
        assignments = [
            TopicPartition(topic, partition, 0) for partition in range(PARTITIONS)
        ]
        consumer.assign(assignments)
        observed = []
        while len(observed) < result.traffic_summary.delivery_count:
            message = consumer.poll(10)
            assert message is not None and message.error() is None
            event = deserialize_fraud_event(message.value())
            assert message.key() == fraud_record_key(event)
            observed.append(event)
        assert Counter(serialize_key(event) for event in observed) == Counter(
            serialize_key(record.event) for record in result.delivery_records
        )
        assert (
            sum(
                consumer.get_watermark_offsets(
                    TopicPartition(topic, partition), cached=False
                )[1]
                for partition in range(PARTITIONS)
            )
            == result.traffic_summary.delivery_count
        )
        assert any(
            count > 1
            for count in Counter(str(event.event_id) for event in observed).values()
        )
        assert projector.state() == ProjectionState.UNINITIALIZED

        class CountingProjector:
            def __init__(self):
                self.results = Counter()

            def state(self):
                return projector.state()

            def begin_rebuild(self):
                projector.begin_rebuild()

            def apply(self, event):
                result = projector.apply(event)
                self.results[result] += 1
                return result

            def mark_ready(self):
                projector.mark_ready()

        counting = CountingProjector()
        assert rebuild_from_kafka(bootstrap, topic, counting) == len(observed)
        assert (
            counting.results[ApplyResult.APPLIED]
            == result.traffic_summary.logical_event_count
        )
        assert (
            counting.results[ApplyResult.DUPLICATE]
            == result.traffic_summary.duplicate_delivery_count
        )
        assert projector.state() == ProjectionState.READY
        reference = ReferenceFeatureProjector()
        for event in result.canonical_events:
            reference.apply(event)
        as_of = result.traffic_summary.latest_occurred_at + timedelta(seconds=1)
        user_devices = {
            event.payload.user_id: event.payload.device_id
            for event in result.canonical_events
            if event.event_type == "account.created"
        }
        for user_id, device_id in user_devices.items():
            assert projector.features_for(
                user_id=user_id, device_id=device_id, as_of=as_of
            ) == reference.features_for(
                user_id=user_id, device_id=device_id, as_of=as_of
            )
        assert (
            client.hlen(f"{namespace}events")
            == result.traffic_summary.logical_event_count
        )
    finally:
        consumer.close()
        keys = list(client.scan_iter(f"{namespace}*"))
        if keys:
            client.delete(*keys)
        client.close()


def serialize_key(event):
    from argus.events.kafka import serialize_fraud_event

    return serialize_fraud_event(event)
