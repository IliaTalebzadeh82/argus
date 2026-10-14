"""Typed Kafka wire boundaries without broker access."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from argus.events.envelope import EventEnvelope
from argus.events.fraud import (
    AccountCreatedPayload,
    ChargebackReceivedPayload,
    PaymentAttemptedPayload,
    PaymentFailedPayload,
    TransactionCompletedPayload,
)
from argus.events.kafka import (
    deserialize_fraud_event,
    fraud_record_key,
    serialize_fraud_event,
)

PAYLOADS = [
    ("account.created", AccountCreatedPayload(user_id="u", device_id="d"), "u"),
    (
        "payment.attempted",
        PaymentAttemptedPayload(payment_id="p", transaction_id="t", user_id="u"),
        "p",
    ),
    (
        "payment.failed",
        PaymentFailedPayload(payment_id="p", transaction_id="t", user_id="u"),
        "p",
    ),
    (
        "transaction.completed",
        TransactionCompletedPayload(transaction_id="t", user_id="u"),
        "t",
    ),
    (
        "chargeback.received",
        ChargebackReceivedPayload(chargeback_id="c", transaction_id="t", user_id="u"),
        "c",
    ),
]


@pytest.mark.parametrize(("kind", "payload", "subject"), PAYLOADS)
def test_typed_round_trip_and_key(kind: str, payload: object, subject: str) -> None:
    now = datetime(2026, 10, 14, tzinfo=UTC)
    event = EventEnvelope[type(payload)](
        event_id=uuid4(),
        event_type=kind,
        event_version=1,
        occurred_at=now,
        produced_at=now,
        producer="test",
        trace_id="trace",
        subject_id=subject,
        payload=payload,
    )
    wire = serialize_fraud_event(event)
    restored = deserialize_fraud_event(wire)
    assert restored == event
    assert type(restored.payload) is type(payload)
    assert fraud_record_key(restored) == b"u"
    assert wire == serialize_fraud_event(event)


def test_reject_invalid_wire() -> None:
    kind, payload, subject = PAYLOADS[1]
    now = datetime(2026, 10, 14, tzinfo=UTC)
    valid = EventEnvelope[type(payload)](
        event_id=uuid4(),
        event_type=kind,
        event_version=1,
        occurred_at=now,
        produced_at=now,
        producer="test",
        trace_id="trace",
        subject_id=subject,
        payload=payload,
    )
    document = json.loads(serialize_fraud_event(valid))
    variants = []
    for key, value in (
        ("event_type", "other"),
        ("event_version", 2),
        ("subject_id", "other"),
    ):
        changed = dict(document)
        changed[key] = value
        variants.append(json.dumps(changed).encode())
    changed = dict(document)
    changed["payload"] = {**document["payload"], "extra": 1}
    variants.append(json.dumps(changed).encode())
    changed = dict(document)
    changed["extra"] = 1
    variants.append(json.dumps(changed).encode())
    variants.extend([b"{", b"[]", b'{"event_type":"x","event_type":"y"}'])
    for wire in variants:
        with pytest.raises((ValueError, TypeError)):
            deserialize_fraud_event(wire)
