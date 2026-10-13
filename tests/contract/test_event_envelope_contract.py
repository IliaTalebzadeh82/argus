from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from argus.events import EventEnvelope


class ExamplePayload(BaseModel):
    count: int


def test_retry_reuses_logical_event_identity_across_json_deliveries() -> None:
    event_id = UUID("00000000-0000-4000-8000-000000000001")
    original = EventEnvelope[ExamplePayload](
        event_id=event_id,
        event_type="example.occurred",
        event_version=1,
        occurred_at=datetime(2026, 10, 13, 12, tzinfo=UTC),
        produced_at=datetime(2026, 10, 13, 12, 0, 1, tzinfo=UTC),
        producer="example-service",
        trace_id="opaque-correlation-value",
        subject_id="entity-1",
        payload=ExamplePayload(count=3),
    )

    wire_json = original.model_dump_json()
    retry = EventEnvelope[ExamplePayload].model_validate_json(wire_json)

    assert retry.event_id == original.event_id == event_id
    assert retry == original
