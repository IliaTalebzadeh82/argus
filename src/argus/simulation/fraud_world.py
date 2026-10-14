"""Pure coordinated fraud scenario; relationships remain simulator-only."""

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from argus.domain.models import Device, Money, PaymentAttempt, Transaction, UserAccount
from argus.events.envelope import EventEnvelope
from argus.events.fraud import (
    AccountCreatedPayload,
    ChargebackReceivedPayload,
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
class FraudScenarioConfig:
    ring_count: int
    accounts_per_ring: int
    payments_per_account: int
    merchant_count: int
    payment_failure_probability: float
    chargeback_probability: float
    min_amount_minor: int
    max_amount_minor: int
    currency: str
    ring_spacing: timedelta
    account_spacing: timedelta
    first_payment_delay: timedelta
    payment_spacing: timedelta
    terminal_delay: timedelta
    chargeback_delay: timedelta

    def __post_init__(self) -> None:
        for name in (
            "ring_count",
            "accounts_per_ring",
            "payments_per_account",
            "merchant_count",
            "min_amount_minor",
            "max_amount_minor",
        ):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"{name} must be an integer, not bool")
        if (
            self.ring_count <= 0
            or self.accounts_per_ring <= 1
            or self.merchant_count <= 0
        ):
            raise ValueError(
                "rings and merchants must be positive; rings need multiple accounts"
            )
        if self.payments_per_account < 0:
            raise ValueError("payments_per_account must be nonnegative")
        if self.min_amount_minor < 0 or self.max_amount_minor < self.min_amount_minor:
            raise ValueError("invalid amount range")
        for name in ("payment_failure_probability", "chargeback_probability"):
            value = getattr(self, name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{name} must be finite and between 0 and 1")
            object.__setattr__(self, name, float(value))
        if not isinstance(self.currency, str):
            raise TypeError("currency must be a string")
        object.__setattr__(
            self, "currency", Money(amount_minor=0, currency=self.currency).currency
        )
        for name in (
            "ring_spacing",
            "account_spacing",
            "first_payment_delay",
            "payment_spacing",
            "terminal_delay",
            "chargeback_delay",
        ):
            value = getattr(self, name)
            if not isinstance(value, timedelta):
                raise TypeError(f"{name} must be a timedelta")
            if value < timedelta(0):
                raise ValueError(f"{name} must be nonnegative")

    def to_json(self) -> str:
        return json.dumps(
            {
                "ring_count": self.ring_count,
                "accounts_per_ring": self.accounts_per_ring,
                "payments_per_account": self.payments_per_account,
                "merchant_count": self.merchant_count,
                "payment_failure_probability": self.payment_failure_probability,
                "chargeback_probability": self.chargeback_probability,
                "min_amount_minor": self.min_amount_minor,
                "max_amount_minor": self.max_amount_minor,
                "currency": self.currency,
                "ring_spacing_us": self.ring_spacing // timedelta(microseconds=1),
                "account_spacing_us": self.account_spacing // timedelta(microseconds=1),
                "first_payment_delay_us": self.first_payment_delay
                // timedelta(microseconds=1),
                "payment_spacing_us": self.payment_spacing // timedelta(microseconds=1),
                "terminal_delay_us": self.terminal_delay // timedelta(microseconds=1),
                "chargeback_delay_us": self.chargeback_delay
                // timedelta(microseconds=1),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class FraudRingTruth:
    ring_id: str
    account_farm_id: str
    member_user_ids: tuple[str, ...]
    shared_device_id: str
    shared_card_id: str
    shared_promo_code: str


@dataclass(frozen=True, slots=True)
class SyntheticCardUse:
    ring_id: str
    card_id: str
    user_id: str
    transaction_id: str


@dataclass(frozen=True, slots=True)
class SyntheticPromoRedemption:
    ring_id: str
    promo_code: str
    user_id: str
    transaction_id: str
    redeemed_at: datetime


@dataclass(frozen=True, slots=True)
class FraudScenarioResult:
    manifest: SimulationManifest
    config: FraudScenarioConfig
    users: tuple[UserAccount, ...]
    devices: tuple[Device, ...]
    transactions: tuple[Transaction, ...]
    payment_attempts: tuple[PaymentAttempt, ...]
    ring_truth: tuple[FraudRingTruth, ...]
    card_uses: tuple[SyntheticCardUse, ...]
    promo_redemptions: tuple[SyntheticPromoRedemption, ...]
    event_records: tuple[SimulationRecord[EventEnvelope[FraudPayload]], ...]


def run_fraud_scenario(
    kernel: SimulationKernel, config: FraudScenarioConfig
) -> FraudScenarioResult:
    """Plan in ring/member/payment order; emit in global event-time order."""
    manifest = kernel.manifest
    run_identity = scenario_identity(manifest, "fraud", config.to_json())
    merchants = tuple(
        f"merchant-{number:06d}" for number in range(1, config.merchant_count + 1)
    )
    users: list[UserAccount] = []
    devices: list[Device] = []
    transactions: list[Transaction] = []
    attempts: list[PaymentAttempt] = []
    rings: list[FraudRingTruth] = []
    card_uses: list[SyntheticCardUse] = []
    promos: list[SyntheticPromoRedemption] = []
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
        schedule.append((at, len(schedule), event))

    for ring_index in range(config.ring_count):
        ring_at = manifest.starts_at + ring_index * config.ring_spacing
        ring_id = kernel.ids.next("ring")
        farm_id = kernel.ids.next("farm")
        device_id = kernel.ids.next("device")
        card_id = kernel.ids.next("card")
        promo_code = kernel.ids.next("promo")
        devices.append(Device(device_id=device_id, first_seen_at=ring_at))
        members: list[str] = []
        for account_index in range(config.accounts_per_ring):
            user_id = kernel.ids.next("user")
            members.append(user_id)
            account_at = ring_at + account_index * config.account_spacing
            users.append(UserAccount(user_id=user_id, created_at=account_at))
            plan(
                "account.created",
                user_id,
                f"account:{user_id}",
                AccountCreatedPayload(user_id=user_id, device_id=device_id),
                account_at,
            )
            amount_rng = kernel.random.stream(f"fraud-payments:{user_id}:amount")
            merchant_rng = kernel.random.stream(f"fraud-payments:{user_id}:merchant")
            outcome_rng = kernel.random.stream(f"fraud-payments:{user_id}:outcome")
            chargeback_rng = kernel.random.stream(
                f"fraud-payments:{user_id}:chargeback"
            )
            for payment_index in range(config.payments_per_account):
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
                transactions.append(transaction)
                attempts.append(
                    PaymentAttempt(
                        payment_id=payment_id,
                        transaction_id=transaction_id,
                        attempted_at=at,
                    )
                )
                card_uses.append(
                    SyntheticCardUse(
                        ring_id=ring_id,
                        card_id=card_id,
                        user_id=user_id,
                        transaction_id=transaction_id,
                    )
                )
                if payment_index == 0:
                    promos.append(
                        SyntheticPromoRedemption(
                            ring_id=ring_id,
                            promo_code=promo_code,
                            user_id=user_id,
                            transaction_id=transaction_id,
                            redeemed_at=at,
                        )
                    )
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
                    if chargeback_rng.random() < config.chargeback_probability:
                        chargeback_id = kernel.ids.next(f"chargeback-{user_id}")
                        plan(
                            "chargeback.received",
                            chargeback_id,
                            trace_id,
                            ChargebackReceivedPayload(
                                chargeback_id=chargeback_id,
                                transaction_id=transaction_id,
                                user_id=user_id,
                            ),
                            terminal_at + config.chargeback_delay,
                        )
        rings.append(
            FraudRingTruth(
                ring_id=ring_id,
                account_farm_id=farm_id,
                member_user_ids=tuple(members),
                shared_device_id=device_id,
                shared_card_id=card_id,
                shared_promo_code=promo_code,
            )
        )

    records = []
    for at, _, event in sorted(schedule, key=lambda item: (item[0], item[1])):
        kernel.clock.advance(at - kernel.clock.now())
        records.append(kernel.emit(event))
    return FraudScenarioResult(
        manifest=manifest,
        config=config,
        users=tuple(users),
        devices=tuple(devices),
        transactions=tuple(transactions),
        payment_attempts=tuple(attempts),
        ring_truth=tuple(rings),
        card_uses=tuple(card_uses),
        promo_redemptions=tuple(promos),
        event_records=tuple(records),
    )
