"""Canonical fraud-event wire format and acknowledged Kafka publishing."""

import json

from confluent_kafka import Producer

from argus.events.envelope import EventEnvelope
from argus.events.features import canonical_event_identity
from argus.events.fraud import FRAUD_CONTRACTS, FraudPayload, validate_fraud_event

FRAUD_TOPIC = "argus.fraud-events.v1"


def serialize_fraud_event(event: EventEnvelope[FraudPayload]) -> bytes:
    validate_fraud_event(event)
    return canonical_event_identity(event).encode("utf-8")


def deserialize_fraud_event(data: bytes) -> EventEnvelope[FraudPayload]:
    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    document = json.loads(data, object_pairs_hook=unique_pairs)
    if not isinstance(document, dict):
        raise ValueError("fraud event must be a JSON object")
    kind = document.get("event_type")
    version = document.get("event_version")
    if type(kind) is not str or type(version) is not int or version != 1:
        raise ValueError("unsupported fraud event type or version")
    contract = FRAUD_CONTRACTS.get(kind)
    if contract is None:
        raise ValueError("unsupported fraud event type or version")
    payload_type, _ = contract
    event = EventEnvelope[payload_type].model_validate(document)
    validate_fraud_event(event)
    return event


def fraud_record_key(event: EventEnvelope[FraudPayload]) -> bytes:
    validate_fraud_event(event)
    return event.payload.user_id.encode("utf-8")


class KafkaFraudEventProducer:
    def __init__(self, bootstrap_servers: str, *, topic: str = FRAUD_TOPIC) -> None:
        self.topic = topic
        self.client = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "enable.idempotence": True,
                "acks": "all",
            }
        )

    def publish(self, event: EventEnvelope[FraudPayload]) -> None:
        value = serialize_fraud_event(event)
        key = fraud_record_key(event)
        delivery: list[object] = []

        def on_delivery(error: object, message: object) -> None:
            delivery.append(error)

        self.client.produce(self.topic, key=key, value=value, on_delivery=on_delivery)
        if self.client.flush(30) != 0 or not delivery:
            raise TimeoutError("Kafka delivery acknowledgement timed out")
        if delivery[0] is not None:
            raise RuntimeError(f"Kafka delivery failed: {delivery[0]}")
