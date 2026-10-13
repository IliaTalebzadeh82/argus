"""The facts and results of a deterministic fraud evaluation."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)


def aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def reject_numeric_time(value: object) -> object:
    if not isinstance(value, (datetime, str)):
        raise ValueError("timestamp must be an aware datetime or ISO 8601 string")
    return value


Timestamp = Annotated[
    datetime, BeforeValidator(reject_numeric_time), AfterValidator(aware_utc)
]
Identifier = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)
]
SignalCode = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9_]*$")
]
ReasonCode = Annotated[
    str, StringConstraints(strict=True, pattern=r"^[A-Z][A-Z0-9_]*$")
]


class Snapshot(BaseModel):
    """A frozen, closed domain value; persistence may still change separately."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Money(Snapshot):
    amount_minor: StrictInt = Field(ge=0)
    currency: StrictStr

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
            raise ValueError("currency must be a three-letter ASCII code")
        return normalized


class UserAccount(Snapshot):
    user_id: Identifier
    created_at: Timestamp


class Device(Snapshot):
    device_id: Identifier
    first_seen_at: Timestamp


class Transaction(Snapshot):
    transaction_id: Identifier
    user_id: Identifier
    merchant_id: Identifier
    amount: Money
    created_at: Timestamp


class PaymentAttempt(Snapshot):
    payment_id: Identifier
    transaction_id: Identifier
    attempted_at: Timestamp


FiniteFloat = Annotated[StrictFloat, Field(allow_inf_nan=False)]
SignalValue = StrictBool | StrictInt | FiniteFloat | StrictStr


class RiskSignal(Snapshot):
    code: SignalCode
    value: SignalValue
    observed_at: Timestamp
    source: Identifier


class DecisionAction(StrEnum):
    ALLOW = "ALLOW"
    CHALLENGE = "CHALLENGE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class Decision(Snapshot):
    decision_id: Identifier
    subject_id: Identifier
    action: DecisionAction
    decided_at: Timestamp
    reason_codes: tuple[ReasonCode, ...] = Field(min_length=1)


class DecisionContext(Snapshot):
    """Related snapshots supplied to future rules, without evaluation behavior."""

    user: UserAccount
    transaction: Transaction
    payment_attempt: PaymentAttempt
    devices: tuple[Device, ...] = ()
    risk_signals: tuple[RiskSignal, ...] = ()

    @model_validator(mode="after")
    def check_references(self) -> "DecisionContext":
        if self.transaction.user_id != self.user.user_id:
            raise ValueError("transaction user_id does not match user")
        if self.payment_attempt.transaction_id != self.transaction.transaction_id:
            raise ValueError("payment transaction_id does not match transaction")
        return self
