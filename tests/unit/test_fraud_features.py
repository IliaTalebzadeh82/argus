from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from argus.events.envelope import EventEnvelope
from argus.events.features import (
    ApplyResult,
    EventIdentityConflict,
    ReferenceFeatureProjector,
)
from argus.events.fraud import (
    AccountCreatedPayload,
    ChargebackReceivedPayload,
    PaymentAttemptedPayload,
    PaymentFailedPayload,
    TransactionCompletedPayload,
    validate_fraud_event,
)

T = datetime(2026, 10, 14, 12, tzinfo=UTC)


def event(
    number: int,
    kind: str,
    payload: object,
    *,
    occurred_at: datetime = T,
    produced_at: datetime | None = None,
    subject_id: str | None = None,
    version: int = 1,
) -> EventEnvelope:
    subjects = {
        "account.created": "user_id",
        "payment.attempted": "payment_id",
        "payment.failed": "payment_id",
        "transaction.completed": "transaction_id",
        "chargeback.received": "chargeback_id",
    }
    return EventEnvelope[type(payload)](
        event_id=UUID(int=number),
        event_type=kind,
        event_version=version,
        occurred_at=occurred_at,
        produced_at=produced_at or T,
        producer="simulator",
        trace_id="trace-1",
        subject_id=subject_id or getattr(payload, subjects[kind]),
        payload=payload,
    )


CASES = [
    ("account.created", AccountCreatedPayload(user_id="u", device_id="d")),
    (
        "payment.attempted",
        PaymentAttemptedPayload(payment_id="p", transaction_id="t", user_id="u"),
    ),
    (
        "payment.failed",
        PaymentFailedPayload(payment_id="p", transaction_id="t", user_id="u"),
    ),
    (
        "transaction.completed",
        TransactionCompletedPayload(transaction_id="t", user_id="u"),
    ),
    (
        "chargeback.received",
        ChargebackReceivedPayload(chargeback_id="c", transaction_id="t", user_id="u"),
    ),
]


@pytest.mark.parametrize(("kind", "payload"), CASES)
def test_event_contracts(kind: str, payload: object) -> None:
    valid = event(1, kind, payload)
    validate_fraud_event(valid)
    assert valid.event_type == kind and valid.event_version == 1
    with pytest.raises(ValueError):
        validate_fraud_event(event(2, kind, payload, version=2))
    with pytest.raises(ValueError):
        validate_fraud_event(event(3, kind, payload, subject_id="other"))
    with pytest.raises(ValueError):
        validate_fraud_event(
            event(4, kind, AccountCreatedPayload(user_id="u"), subject_id="u")
            if kind != "account.created"
            else event(
                4,
                kind,
                PaymentFailedPayload(payment_id="p", transaction_id="t", user_id="u"),
                subject_id="u",
            )
        )


@pytest.mark.parametrize(
    "payload_type,data",
    [
        (AccountCreatedPayload, {"user_id": " ", "device_id": "d"}),
        (
            PaymentAttemptedPayload,
            {"payment_id": "", "transaction_id": "t", "user_id": "u"},
        ),
        (
            PaymentFailedPayload,
            {"payment_id": "p", "transaction_id": "t", "user_id": ""},
        ),
        (TransactionCompletedPayload, {"transaction_id": "", "user_id": "u"}),
        (
            ChargebackReceivedPayload,
            {"chargeback_id": "", "transaction_id": "t", "user_id": "u"},
        ),
        (AccountCreatedPayload, {"user_id": "u", "extra": 1}),
    ],
)
def test_payload_rejects_bad_identifier_or_extra(
    payload_type: type, data: dict
) -> None:
    with pytest.raises(ValidationError):
        payload_type.model_validate(data)


def test_naive_event_time_and_query_time_rejected() -> None:
    with pytest.raises(ValidationError):
        event(
            1,
            "account.created",
            AccountCreatedPayload(user_id="u"),
            occurred_at=T.replace(tzinfo=None),
        )
    with pytest.raises(ValidationError):
        ReferenceFeatureProjector().features_for(
            user_id="u", device_id="d", as_of=T.replace(tzinfo=None)
        )


def test_windows_produced_time_future_events_and_missing_device() -> None:
    projector = ReferenceFeatureProjector()
    points = [
        T - timedelta(minutes=10, microseconds=1),
        T - timedelta(minutes=10),
        T - timedelta(minutes=10) + timedelta(microseconds=1),
        T,
        T + timedelta(microseconds=1),
    ]
    for n, at in enumerate(points, 1):
        assert (
            projector.apply(
                event(
                    n,
                    "payment.attempted",
                    PaymentAttemptedPayload(
                        payment_id=f"p{n}", transaction_id="t", user_id="u"
                    ),
                    occurred_at=at,
                    produced_at=T + timedelta(days=3),
                )
            )
            == ApplyResult.APPLIED
        )
    for n, at in enumerate(
        [
            T - timedelta(hours=1, microseconds=1),
            T - timedelta(hours=1),
            T - timedelta(hours=1) + timedelta(microseconds=1),
            T,
            T + timedelta(microseconds=1),
        ],
        6,
    ):
        projector.apply(
            event(
                n,
                "payment.failed",
                PaymentFailedPayload(
                    payment_id=f"p{n}", transaction_id="t", user_id="u"
                ),
                occurred_at=at,
                produced_at=T - timedelta(days=3),
            )
        )
    snapshot = projector.features_for(user_id="u", device_id=None, as_of=T)
    assert (
        snapshot.payments_10m,
        snapshot.failed_payments_1h,
        snapshot.accounts_on_device,
    ) == (2, 2, None)
    assert (
        projector.features_for(
            user_id="u", device_id="unknown", as_of=T
        ).accounts_on_device
        == 0
    )
    assert snapshot == projector.features_for(user_id="u", device_id=None, as_of=T)
    with pytest.raises(ValidationError):
        snapshot.payments_10m = 10


def test_distinct_accounts_duplicates_reordering_and_replay() -> None:
    history = [
        event(
            1,
            "account.created",
            AccountCreatedPayload(user_id="a", device_id="d"),
            occurred_at=T - timedelta(hours=2),
        ),
        event(2, "account.created", AccountCreatedPayload(user_id="b", device_id="d")),
        event(3, "account.created", AccountCreatedPayload(user_id="a", device_id="d")),
        event(
            4, "account.created", AccountCreatedPayload(user_id="a", device_id="other")
        ),
        event(
            5,
            "payment.attempted",
            PaymentAttemptedPayload(payment_id="p", transaction_id="t", user_id="a"),
            occurred_at=T - timedelta(minutes=5),
        ),
        event(
            6,
            "payment.failed",
            PaymentFailedPayload(payment_id="p", transaction_id="t", user_id="a"),
            occurred_at=T - timedelta(minutes=6),
        ),
        event(
            7,
            "transaction.completed",
            TransactionCompletedPayload(transaction_id="t", user_id="a"),
        ),
        event(
            8,
            "chargeback.received",
            ChargebackReceivedPayload(
                chargeback_id="c", transaction_id="t", user_id="a"
            ),
        ),
    ]
    first, replay = ReferenceFeatureProjector(), ReferenceFeatureProjector()
    for item in history:
        assert first.apply(item) == ApplyResult.APPLIED
        assert first.apply(item) == ApplyResult.DUPLICATE
    for item in [history[i] for i in (5, 4, 1, 0, 5, 7, 6, 2, 3, 0, 4)]:
        replay.apply(item)
    for device in ("d", "other", None):
        assert first.features_for(
            user_id="a", device_id=device, as_of=T
        ) == replay.features_for(user_id="a", device_id=device, as_of=T)
    result = first.features_for(user_id="a", device_id="d", as_of=T)
    assert (
        result.payments_10m,
        result.failed_payments_1h,
        result.accounts_on_device,
    ) == (1, 1, 2)
    assert (
        first.features_for(user_id="b", device_id="other", as_of=T).accounts_on_device
        == 1
    )
    assert (
        first.features_for(
            user_id="a", device_id="d", as_of=T - timedelta(hours=3)
        ).accounts_on_device
        == 0
    )


def test_same_id_conflicts_on_payload_type_and_metadata() -> None:
    projector = ReferenceFeatureProjector()
    original = event(
        1,
        "payment.attempted",
        PaymentAttemptedPayload(payment_id="p", transaction_id="t", user_id="u"),
    )
    projector.apply(original)
    assert projector.apply(original) == ApplyResult.DUPLICATE
    changes = [
        event(
            1,
            "payment.attempted",
            PaymentAttemptedPayload(
                payment_id="other", transaction_id="t", user_id="u"
            ),
        ),
        event(
            1,
            "payment.failed",
            PaymentFailedPayload(payment_id="p", transaction_id="t", user_id="u"),
        ),
        event(
            1,
            "payment.attempted",
            original.payload,
            produced_at=T + timedelta(seconds=1),
        ),
    ]
    for changed in changes:
        with pytest.raises(EventIdentityConflict):
            projector.apply(changed)
    assert (
        projector.features_for(user_id="u", device_id=None, as_of=T).payments_10m == 1
    )
