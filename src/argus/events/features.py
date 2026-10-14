"""Exact in-memory event-time reference for the current fraud features."""

from datetime import timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from argus.domain.models import Identifier, Snapshot, Timestamp
from argus.events.envelope import EventEnvelope
from argus.events.fraud import (
    AccountCreatedPayload,
    FraudPayload,
    PaymentAttemptedPayload,
    PaymentFailedPayload,
    validate_fraud_event,
)


class OnlineFeatureSnapshot(Snapshot):
    user_id: Identifier
    device_id: Identifier | None
    as_of: Timestamp
    payments_10m: int = Field(ge=0)
    failed_payments_1h: int = Field(ge=0)
    accounts_on_device: int | None = Field(ge=0)


class ApplyResult(StrEnum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"


class EventIdentityConflict(ValueError):
    """One event ID was assigned to two different recorded facts."""


class ReferenceFeatureProjector:
    """Retain full logical history; queries derive views at explicit event time."""

    def __init__(self) -> None:
        self._events: dict[UUID, EventEnvelope[FraudPayload]] = {}
        self._identities: dict[UUID, dict[str, object]] = {}

    def apply(self, event: EventEnvelope[FraudPayload]) -> ApplyResult:
        validate_fraud_event(event)
        identity = event.model_dump(mode="json", serialize_as_any=True)
        previous = self._identities.get(event.event_id)
        if previous is not None:
            if previous != identity:
                raise EventIdentityConflict(f"conflicting event_id: {event.event_id}")
            return ApplyResult.DUPLICATE
        self._events[event.event_id] = event
        self._identities[event.event_id] = identity
        return ApplyResult.APPLIED

    def features_for(
        self, *, user_id: str, device_id: str | None, as_of: Timestamp
    ) -> OnlineFeatureSnapshot:
        # Validate query inputs and normalize its timestamp before comparison.
        query = OnlineFeatureSnapshot(
            user_id=user_id,
            device_id=device_id,
            as_of=as_of,
            payments_10m=0,
            failed_payments_1h=0,
            accounts_on_device=None if device_id is None else 0,
        )
        payment_start = query.as_of - timedelta(minutes=10)
        failure_start = query.as_of - timedelta(hours=1)
        payments = 0
        failures = 0
        accounts: set[str] = set()
        for event in self._events.values():
            if event.occurred_at > query.as_of:
                continue
            payload = event.payload
            if isinstance(payload, PaymentAttemptedPayload):
                if payload.user_id == user_id and payment_start < event.occurred_at:
                    payments += 1
            elif isinstance(payload, PaymentFailedPayload):
                if payload.user_id == user_id and failure_start < event.occurred_at:
                    failures += 1
            elif isinstance(payload, AccountCreatedPayload):
                if device_id is not None and payload.device_id == device_id:
                    accounts.add(payload.user_id)
        return query.model_copy(
            update={
                "payments_10m": payments,
                "failed_payments_1h": failures,
                "accounts_on_device": None if device_id is None else len(accounts),
            }
        )
