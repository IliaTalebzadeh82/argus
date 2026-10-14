"""Version-one fraud event facts and their envelope contract boundary."""

from pydantic import BaseModel, ConfigDict

from argus.domain.models import Identifier
from argus.events.envelope import EventEnvelope


class FraudPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AccountCreatedPayload(FraudPayload):
    user_id: Identifier
    device_id: Identifier | None = None


class PaymentAttemptedPayload(FraudPayload):
    payment_id: Identifier
    transaction_id: Identifier
    user_id: Identifier


class PaymentFailedPayload(FraudPayload):
    payment_id: Identifier
    transaction_id: Identifier
    user_id: Identifier


class TransactionCompletedPayload(FraudPayload):
    transaction_id: Identifier
    user_id: Identifier


class ChargebackReceivedPayload(FraudPayload):
    chargeback_id: Identifier
    transaction_id: Identifier
    user_id: Identifier


FRAUD_CONTRACTS: dict[str, tuple[type[FraudPayload], str]] = {
    "account.created": (AccountCreatedPayload, "user_id"),
    "payment.attempted": (PaymentAttemptedPayload, "payment_id"),
    "payment.failed": (PaymentFailedPayload, "payment_id"),
    "transaction.completed": (TransactionCompletedPayload, "transaction_id"),
    "chargeback.received": (ChargebackReceivedPayload, "chargeback_id"),
}


def validate_fraud_event(event: EventEnvelope[FraudPayload]) -> None:
    """Reject an unsupported type/version/payload/subject combination."""
    contract = FRAUD_CONTRACTS.get(event.event_type)
    if contract is None or event.event_version != 1:
        raise ValueError("unsupported fraud event type or version")
    payload_type, subject_field = contract
    if type(event.payload) is not payload_type:
        raise ValueError("fraud event payload does not match type")
    if event.subject_id != getattr(event.payload, subject_field):
        raise ValueError("fraud event subject does not match payload")
