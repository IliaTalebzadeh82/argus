"""Synchronous decision orchestration with PostgreSQL as the idempotency boundary."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import model_validator
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from argus.domain.models import (
    Decision,
    DecisionContext,
    Device,
    Identifier,
    PaymentAttempt,
    RiskSignal,
    Snapshot,
    Transaction,
    UserAccount,
)
from argus.events.features import OnlineFeatureSnapshot
from argus.features.redis_projection import ProjectionStateError, ProjectionUnavailable
from argus.fraud.policy import ConservativeDecisionPolicy
from argus.fraud.rules import (
    FailedPaymentVelocityRule,
    PaymentVelocityRule,
    RuleEngine,
    SharedDeviceAccountsRule,
)
from argus.persistence import schema as s
from argus.persistence.records import DecisionRecord
from argus.persistence.repository import PostgresDecisionRepository

FEATURE_SOURCE = "redis_features_v1"

# Demonstration thresholds and signal source. Change membership, thresholds, or
# source only with a rule_set_version bump, even when rule code is unchanged.
DEPLOYED_RULES = RuleEngine(
    rules=(
        PaymentVelocityRule(threshold=5, source=FEATURE_SOURCE),
        SharedDeviceAccountsRule(threshold=3, source=FEATURE_SOURCE),
        FailedPaymentVelocityRule(threshold=3, source=FEATURE_SOURCE),
    ),
    rule_set_id="phase1_payment",
    rule_set_version=2,
)
DEPLOYED_POLICY = ConservativeDecisionPolicy(policy_version=1)


class IdempotencyKeyReused(ValueError):
    pass


class FeaturesUnavailable(RuntimeError):
    """Online feature evidence cannot be read for a new decision."""


class PaymentDecisionInput(Snapshot):
    user: UserAccount
    transaction: Transaction
    payment_attempt: PaymentAttempt
    devices: tuple[Device, ...] = ()
    observed_device_id: Identifier | None = None

    @model_validator(mode="after")
    def check_facts(self) -> "PaymentDecisionInput":
        if self.transaction.user_id != self.user.user_id:
            raise ValueError("transaction user_id does not match user")
        if self.payment_attempt.transaction_id != self.transaction.transaction_id:
            raise ValueError("payment transaction_id does not match transaction")
        if self.observed_device_id is not None and self.observed_device_id not in {
            device.device_id for device in self.devices
        }:
            raise ValueError("observed_device_id must name a supplied device")
        return self


class OnlineFeatureReader(Protocol):
    def features_for(
        self, *, user_id: str, device_id: str | None, as_of: datetime
    ) -> OnlineFeatureSnapshot: ...


def signals_from(snapshot: OnlineFeatureSnapshot) -> tuple[RiskSignal, ...]:
    values = [
        ("payments_10m", snapshot.payments_10m),
        ("failed_payments_1h", snapshot.failed_payments_1h),
    ]
    if snapshot.accounts_on_device is not None:
        values.append(("accounts_on_device", snapshot.accounts_on_device))
    return tuple(
        RiskSignal(
            code=code, value=value, observed_at=snapshot.as_of, source=FEATURE_SOURCE
        )
        for code, value in values
    )


def fingerprint(facts: PaymentDecisionInput) -> str:
    canonical = json.dumps(
        facts.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    replayed: bool


@dataclass
class DecisionService:
    engine: Engine
    feature_reader: OnlineFeatureReader
    rules: RuleEngine = DEPLOYED_RULES
    policy: ConservativeDecisionPolicy = DEPLOYED_POLICY
    id_factory: Callable[[], str] = lambda: str(uuid4())
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def decide(self, facts: PaymentDecisionInput, key: str) -> DecisionResult:
        request_fingerprint = fingerprint(facts)
        # A deferred FK lets the claim precede the audit write. Uniqueness makes
        # concurrent contenders wait for the first transaction to commit/rollback.
        decision_id = self.id_factory()
        with self.engine.begin() as connection:
            claimed = connection.execute(
                insert(s.decision_idempotency)
                .values(
                    idempotency_key=key,
                    request_fingerprint=request_fingerprint,
                    decision_id=decision_id,
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(s.decision_idempotency.c.idempotency_key)
            ).first()
            repository = PostgresDecisionRepository(connection)
            if claimed is None:
                row = connection.execute(
                    select(s.decision_idempotency).where(
                        s.decision_idempotency.c.idempotency_key == key
                    )
                ).one()
                if row.request_fingerprint != request_fingerprint:
                    raise IdempotencyKeyReused(key)
                record = repository.get(row.decision_id)
                if record is None:
                    raise RuntimeError("completed idempotency claim has no decision")
                result = DecisionResult(record.decision, replayed=True)
            else:
                try:
                    snapshot = self.feature_reader.features_for(
                        user_id=facts.user.user_id,
                        device_id=facts.observed_device_id,
                        as_of=facts.payment_attempt.attempted_at,
                    )
                except (RedisError, ProjectionUnavailable, ProjectionStateError) as exc:
                    raise FeaturesUnavailable from exc
                context = DecisionContext(
                    user=facts.user,
                    transaction=facts.transaction,
                    payment_attempt=facts.payment_attempt,
                    devices=facts.devices,
                    risk_signals=signals_from(snapshot),
                )
                evaluation = self.rules.evaluate(context)
                decision = self.policy.decide(
                    evaluation, decision_id=decision_id, decided_at=self.clock()
                )
                repository.record(DecisionRecord(context, evaluation, decision))
                result = DecisionResult(decision, replayed=False)
        # Exiting engine.begin commits; commit errors cannot yield HTTP success.
        return result
