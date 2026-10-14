"""Offset commit result is part of the processing success condition."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from argus.events.envelope import EventEnvelope
from argus.events.features import ApplyResult
from argus.events.fraud import PaymentAttemptedPayload
from argus.events.kafka import serialize_fraud_event
from argus.workers.feature_worker import FeatureWorker


def test_partition_commit_error_surfaces_after_apply() -> None:
    now = datetime(2026, 10, 14, tzinfo=UTC)
    event = EventEnvelope[PaymentAttemptedPayload](
        event_id=uuid4(),
        event_type="payment.attempted",
        event_version=1,
        occurred_at=now,
        produced_at=now,
        producer="test",
        trace_id="trace",
        subject_id="p",
        payload=PaymentAttemptedPayload(
            payment_id="p", transaction_id="t", user_id="u"
        ),
    )
    message = SimpleNamespace(
        error=lambda: None,
        value=lambda: serialize_fraud_event(event),
        key=lambda: b"u",
        topic=lambda: "topic",
        partition=lambda: 0,
        offset=lambda: 4,
    )
    applied = []

    class Projector:
        def apply(self, value):
            applied.append(value)
            return ApplyResult.APPLIED

    class Consumer:
        def commit(self, *, offsets, asynchronous):
            assert offsets[0].offset == 5
            assert asynchronous is False
            return [SimpleNamespace(error=RuntimeError("broker rejected"), offset=5)]

    with pytest.raises(RuntimeError, match="offset commit failed"):
        FeatureWorker(Consumer(), Projector()).process_message(message)
    assert applied == [event]
