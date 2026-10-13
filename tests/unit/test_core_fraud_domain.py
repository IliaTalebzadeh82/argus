from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from argus.domain import (
    Decision,
    DecisionAction,
    DecisionContext,
    Device,
    Money,
    PaymentAttempt,
    RiskSignal,
    Transaction,
    UserAccount,
)

NOW = datetime(2026, 10, 13, 12, tzinfo=UTC)


def user(user_id: str = "user-1") -> UserAccount:
    return UserAccount(user_id=user_id, created_at=NOW)


def transaction(user_id: str = "user-1") -> Transaction:
    return Transaction(
        transaction_id="txn-1",
        user_id=user_id,
        merchant_id="merchant-1",
        amount=Money(amount_minor=1234, currency="eur"),
        created_at=NOW,
    )


def payment(transaction_id: str = "txn-1", payment_id: str = "pay-1") -> PaymentAttempt:
    return PaymentAttempt(
        payment_id=payment_id, transaction_id=transaction_id, attempted_at=NOW
    )


def context(user_id: str = "user-1", device: Device | None = None) -> DecisionContext:
    return DecisionContext(
        user=user(user_id),
        transaction=transaction(user_id),
        payment_attempt=payment(),
        devices=(device,) if device else (),
    )


@pytest.mark.parametrize("bad_id", ["", "   "])
@pytest.mark.parametrize("field", ["user_id", "transaction_id", "merchant_id"])
def test_rejects_empty_identifiers(field: str, bad_id: str) -> None:
    data = transaction().model_dump()
    data[field] = bad_id
    with pytest.raises(ValidationError):
        Transaction.model_validate(data)


def test_money_round_trip_and_zero() -> None:
    money = Money(amount_minor=1234, currency="eur")
    assert money == Money.model_validate_json(money.model_dump_json())
    assert money.currency == "EUR"
    assert Money(amount_minor=0, currency="USD").amount_minor == 0


@pytest.mark.parametrize(
    "data",
    [
        {"amount_minor": -1, "currency": "EUR"},
        {"amount_minor": 12.34, "currency": "EUR"},
        {"amount_minor": True, "currency": "EUR"},
        {"amount_minor": 1234, "currency": "EU"},
        {"amount_minor": 1234, "currency": "€UR"},
    ],
)
def test_money_rejects_invalid_input(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Money.model_validate(data)


@pytest.mark.parametrize(
    "model,field,data",
    [
        (UserAccount, "created_at", {"user_id": "u"}),
        (Device, "first_seen_at", {"device_id": "d"}),
        (Transaction, "created_at", transaction().model_dump()),
        (PaymentAttempt, "attempted_at", payment().model_dump()),
        (
            RiskSignal,
            "observed_at",
            {"code": "count", "value": 2, "source": "features"},
        ),
        (
            Decision,
            "decided_at",
            {
                "decision_id": "d",
                "subject_id": "txn-1",
                "action": "ALLOW",
                "reason_codes": ["CLEAR"],
            },
        ),
    ],
)
def test_rejects_naive_time(model: type, field: str, data: dict[str, object]) -> None:
    data[field] = datetime(2026, 10, 13, 12)
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_offset_time_normalizes_to_utc() -> None:
    offset_time = datetime(2026, 10, 13, 15, tzinfo=timezone(timedelta(hours=3)))
    assert (
        user().created_at == UserAccount(user_id="u", created_at=offset_time).created_at
    )
    assert (
        UserAccount(user_id="u", created_at=offset_time)
        .model_dump_json()
        .endswith('"2026-10-13T12:00:00Z"}')
    )


def test_rejects_numeric_timestamp() -> None:
    with pytest.raises(ValidationError):
        UserAccount(user_id="u", created_at=1_760_357_600)


def test_multiple_payment_attempts_reference_one_transaction() -> None:
    first = payment(payment_id="pay-1")
    second = payment(payment_id="pay-2")
    assert first.payment_id != second.payment_id
    assert first.transaction_id == second.transaction_id == transaction().transaction_id


def test_device_can_appear_for_different_users() -> None:
    shared = Device(device_id="device-1", first_seen_at=NOW)
    assert context("user-1", shared).devices[0] == context("user-2", shared).devices[0]


@pytest.mark.parametrize("mismatch", ["user", "payment"])
def test_context_rejects_mismatched_references(mismatch: str) -> None:
    data = {
        "user": user(),
        "transaction": transaction("other" if mismatch == "user" else "user-1"),
        "payment_attempt": payment("other" if mismatch == "payment" else "txn-1"),
    }
    with pytest.raises(ValidationError):
        DecisionContext.model_validate(data)


def test_decision_action_is_exactly_four_outcomes() -> None:
    assert {action.value for action in DecisionAction} == {
        "ALLOW",
        "CHALLENGE",
        "REVIEW",
        "BLOCK",
    }
    with pytest.raises(ValidationError):
        Decision(
            decision_id="d",
            subject_id="txn-1",
            action="DENY",
            decided_at=NOW,
            reason_codes=("CLEAR",),
        )


def test_decision_is_immutable_and_has_reasons() -> None:
    decision = Decision(
        decision_id="d",
        subject_id="txn-1",
        action="ALLOW",
        decided_at=NOW,
        reason_codes=("CLEAR",),
    )
    with pytest.raises(ValidationError):
        decision.action = DecisionAction.BLOCK
    with pytest.raises(ValidationError):
        Decision(
            decision_id="d",
            subject_id="txn-1",
            action="ALLOW",
            decided_at=NOW,
            reason_codes=(),
        )
    with pytest.raises(ValidationError):
        Decision(
            decision_id="d",
            subject_id="txn-1",
            action="ALLOW",
            decided_at=NOW,
            reason_codes=("human prose",),
        )


@pytest.mark.parametrize("value", [True, 3, 1.5, "low"])
def test_risk_signal_supported_scalars(value: object) -> None:
    signal = RiskSignal(
        code="account_age_hours",
        value=value,
        observed_at=NOW,
        source="account_features",
    )
    assert signal.value == value
    assert type(signal.value) is type(value)
    assert RiskSignal.model_validate_json(signal.model_dump_json()) == signal


@pytest.mark.parametrize(
    "data",
    [
        {"code": "", "value": 1, "source": "features"},
        {"code": "BAD CODE", "value": 1, "source": "features"},
        {"code": "count", "value": 1, "source": ""},
        {"code": "count", "value": [], "source": "features"},
        {"code": "count", "value": {"nested": 1}, "source": "features"},
        {"code": "count", "value": float("nan"), "source": "features"},
        {"code": "count", "value": float("inf"), "source": "features"},
    ],
)
def test_risk_signal_rejects_bad_data(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RiskSignal.model_validate({**data, "observed_at": NOW})
