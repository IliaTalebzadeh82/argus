"""Deterministic legitimate accounts and payment behavior."""

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from argus.domain.models import Device, Money, PaymentAttempt, Transaction, UserAccount
from argus.events.envelope import EventEnvelope
from argus.events.fraud import (
    AccountCreatedPayload,
    FraudPayload,
    PaymentAttemptedPayload,
    PaymentFailedPayload,
    TransactionCompletedPayload,
)
from argus.simulation.events import scenario_identity, simulation_event
from argus.simulation.kernel import (
    SimulationKernel,
    SimulationManifest,
    SimulationRecord,
)


@dataclass(frozen=True, slots=True)
class LegitimateScenarioConfig:
    user_count: int
    payments_per_user: int
    merchant_count: int
    payment_failure_probability: float
    min_amount_minor: int
    max_amount_minor: int
    currency: str
    account_spacing: timedelta
    first_payment_delay: timedelta
    payment_spacing: timedelta
    terminal_delay: timedelta

    def __post_init__(self) -> None:
        for name in (
            "user_count",
            "payments_per_user",
            "merchant_count",
            "min_amount_minor",
            "max_amount_minor",
        ):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"{name} must be an integer, not bool")
        if self.user_count <= 0 or self.merchant_count <= 0:
            raise ValueError("user_count and merchant_count must be positive")
        if self.payments_per_user < 0:
            raise ValueError("payments_per_user must be nonnegative")
        if self.min_amount_minor < 0 or self.max_amount_minor < self.min_amount_minor:
            raise ValueError("invalid amount range")
        probability = self.payment_failure_probability
        if (
            type(probability) not in (int, float)
            or not math.isfinite(probability)
            or not 0 <= probability <= 1
        ):
            raise ValueError(
                "payment_failure_probability must be finite and between 0 and 1"
            )
        object.__setattr__(self, "payment_failure_probability", float(probability))
        if not isinstance(self.currency, str):
            raise TypeError("currency must be a string")
        object.__setattr__(
            self, "currency", Money(amount_minor=0, currency=self.currency).currency
        )
        for name in (
            "account_spacing",
            "first_payment_delay",
            "payment_spacing",
            "terminal_delay",
        ):
            value = getattr(self, name)
            if not isinstance(value, timedelta):
                raise TypeError(f"{name} must be a timedelta")
            if value < timedelta(0):
                raise ValueError(f"{name} must be nonnegative")

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_count": self.user_count,
                "payments_per_user": self.payments_per_user,
                "merchant_count": self.merchant_count,
                "payment_failure_probability": self.payment_failure_probability,
                "min_amount_minor": self.min_amount_minor,
                "max_amount_minor": self.max_amount_minor,
                "currency": self.currency,
                "account_spacing_us": self.account_spacing // timedelta(microseconds=1),
                "first_payment_delay_us": self.first_payment_delay
                // timedelta(microseconds=1),
                "payment_spacing_us": self.payment_spacing // timedelta(microseconds=1),
                "terminal_delay_us": self.terminal_delay // timedelta(microseconds=1),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class LegitimateScenarioResult:
    manifest: SimulationManifest
    config: LegitimateScenarioConfig
    users: tuple[UserAccount, ...]
    devices: tuple[Device, ...]
    transactions: tuple[Transaction, ...]
    payment_attempts: tuple[PaymentAttempt, ...]
    event_records: tuple[SimulationRecord[EventEnvelope[FraudPayload]], ...]


def run_legitimate_scenario(
    kernel: SimulationKernel, config: LegitimateScenarioConfig
) -> LegitimateScenarioResult:
    """Plan in user/payment order, then emit events in event-time order."""
    manifest = kernel.manifest
    run_identity = scenario_identity(manifest, "legitimate", config.to_json())
    merchants = tuple(
        f"merchant-{number:06d}" for number in range(1, config.merchant_count + 1)
    )
    users: list[UserAccount] = []
    devices: list[Device] = []
    transactions: list[Transaction] = []
    attempts: list[PaymentAttempt] = []
    schedule: list[tuple[datetime, int, EventEnvelope[FraudPayload]]] = []

    def plan(
        event_type: str,
        subject_id: str,
        trace_id: str,
        payload: FraudPayload,
        at: datetime,
    ) -> None:
        event = simulation_event(
            run_identity, event_type, subject_id, trace_id, payload, at
        )
        schedule.append((event.occurred_at, len(schedule), event))

    for user_index in range(config.user_count):
        user_id = kernel.ids.next("user")
        device_id = kernel.ids.next("device")
        account_at = manifest.starts_at + user_index * config.account_spacing
        users.append(UserAccount(user_id=user_id, created_at=account_at))
        devices.append(Device(device_id=device_id, first_seen_at=account_at))
        plan(
            "account.created",
            user_id,
            f"account:{user_id}",
            AccountCreatedPayload(user_id=user_id, device_id=device_id),
            account_at,
        )

        amount_rng = kernel.random.stream(f"payments:{user_id}:amount")
        merchant_rng = kernel.random.stream(f"payments:{user_id}:merchant")
        outcome_rng = kernel.random.stream(f"payments:{user_id}:outcome")
        for payment_index in range(config.payments_per_user):
            at = (
                account_at
                + config.first_payment_delay
                + payment_index * config.payment_spacing
            )
            transaction_id = kernel.ids.next(f"transaction-{user_id}")
            payment_id = kernel.ids.next(f"payment-{user_id}")
            transaction = Transaction(
                transaction_id=transaction_id,
                user_id=user_id,
                merchant_id=merchant_rng.choice(merchants),
                amount=Money(
                    amount_minor=amount_rng.randint(
                        config.min_amount_minor, config.max_amount_minor
                    ),
                    currency=config.currency,
                ),
                created_at=at,
            )
            attempt = PaymentAttempt(
                payment_id=payment_id, transaction_id=transaction_id, attempted_at=at
            )
            transactions.append(transaction)
            attempts.append(attempt)
            trace_id = f"payment:{payment_id}"
            plan(
                "payment.attempted",
                payment_id,
                trace_id,
                PaymentAttemptedPayload(
                    payment_id=payment_id,
                    transaction_id=transaction_id,
                    user_id=user_id,
                ),
                at,
            )
            terminal_at = at + config.terminal_delay
            if outcome_rng.random() < config.payment_failure_probability:
                plan(
                    "payment.failed",
                    payment_id,
                    trace_id,
                    PaymentFailedPayload(
                        payment_id=payment_id,
                        transaction_id=transaction_id,
                        user_id=user_id,
                    ),
                    terminal_at,
                )
            else:
                plan(
                    "transaction.completed",
                    transaction_id,
                    trace_id,
                    TransactionCompletedPayload(
                        transaction_id=transaction_id, user_id=user_id
                    ),
                    terminal_at,
                )

    records = []
    for at, _, event in sorted(schedule, key=lambda item: (item[0], item[1])):
        kernel.clock.advance(at - kernel.clock.now())
        records.append(kernel.emit(event))
    return LegitimateScenarioResult(
        manifest=manifest,
        config=config,
        users=tuple(users),
        devices=tuple(devices),
        transactions=tuple(transactions),
        payment_attempts=tuple(attempts),
        event_records=tuple(records),
    )
