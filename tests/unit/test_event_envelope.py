from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from argus.events import EventEnvelope


class ExamplePayload(BaseModel):
    count: int


def event_data() -> dict[str, object]:
    return {
        "event_id": UUID("00000000-0000-4000-8000-000000000001"),
        "event_type": "example.occurred",
        "event_version": 1,
        "occurred_at": datetime(2026, 10, 13, 12, tzinfo=UTC),
        "produced_at": datetime(2026, 10, 13, 12, 0, 1, tzinfo=UTC),
        "producer": "example-service",
        "trace_id": "opaque-correlation-value",
        "subject_id": "entity-1",
        "payload": {"count": 3},
    }


def test_typed_construction_and_json_round_trip() -> None:
    event = EventEnvelope[ExamplePayload].model_validate(event_data())

    assert isinstance(event.payload, ExamplePayload)
    assert event.payload.count == 3
    wire_json = event.model_dump_json()
    restored = EventEnvelope[ExamplePayload].model_validate_json(wire_json)
    assert restored == event


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_version", 0),
        ("event_version", -1),
        ("event_type", "  "),
        ("producer", ""),
        ("trace_id", "  "),
        ("subject_id", ""),
        ("occurred_at", datetime(2026, 10, 13, 12)),
        ("produced_at", datetime(2026, 10, 13, 12)),
        ("payload", {"count": "invalid"}),
    ],
)
def test_rejects_invalid_fields(field: str, value: object) -> None:
    data = event_data()
    data[field] = value

    with pytest.raises(ValidationError):
        EventEnvelope[ExamplePayload].model_validate(data)


def test_rejects_missing_event_id_and_unknown_envelope_field() -> None:
    data = event_data()
    del data["event_id"]
    data["subjectid"] = "entity-1"

    with pytest.raises(ValidationError) as exc:
        EventEnvelope[ExamplePayload].model_validate(data)

    assert {error["type"] for error in exc.value.errors()} == {
        "missing",
        "extra_forbidden",
    }


def test_envelope_is_frozen() -> None:
    event = EventEnvelope[ExamplePayload].model_validate(event_data())

    with pytest.raises(ValidationError):
        event.event_type = "other.occurred"


def test_offset_timestamps_normalize_to_utc() -> None:
    data = event_data()
    offset = timezone(timedelta(hours=3))
    data["occurred_at"] = datetime(2026, 10, 13, 15, tzinfo=offset)
    event = EventEnvelope[ExamplePayload].model_validate(data)

    assert event.occurred_at == datetime(2026, 10, 13, 12, tzinfo=UTC)
    assert '"occurred_at":"2026-10-13T12:00:00Z"' in event.model_dump_json()


def test_production_time_can_precede_event_time() -> None:
    data = event_data()
    data["produced_at"] = datetime(2026, 10, 13, 11, tzinfo=UTC)

    event = EventEnvelope[ExamplePayload].model_validate(data)
    assert event.produced_at < event.occurred_at
