"""Common envelope for logical events, independent of their transport."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EventEnvelope[PayloadT: BaseModel](BaseModel):
    """A typed event whose identity is supplied by its producer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    event_type: NonEmptyString
    event_version: int = Field(ge=1)
    occurred_at: datetime
    produced_at: datetime
    producer: NonEmptyString
    trace_id: NonEmptyString
    subject_id: NonEmptyString
    payload: PayloadT

    @field_validator("occurred_at", "produced_at")
    @classmethod
    def require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
