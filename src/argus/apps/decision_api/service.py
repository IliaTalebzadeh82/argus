"""Synchronous decision orchestration with PostgreSQL as the idempotency boundary."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from argus.domain.models import Decision, DecisionContext
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

# Demonstration thresholds and signal source. Change membership, thresholds, or
# source only with a rule_set_version bump, even when rule code is unchanged.
DEPLOYED_RULES = RuleEngine(
    rules=(
        PaymentVelocityRule(threshold=5, source="caller"),
        SharedDeviceAccountsRule(threshold=3, source="caller"),
        FailedPaymentVelocityRule(threshold=3, source="caller"),
    ),
    rule_set_id="phase1_payment",
    rule_set_version=1,
)
DEPLOYED_POLICY = ConservativeDecisionPolicy(policy_version=1)


class IdempotencyKeyReused(ValueError):
    pass


def fingerprint(context: DecisionContext) -> str:
    canonical = json.dumps(
        context.model_dump(mode="json"),
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
    rules: RuleEngine = DEPLOYED_RULES
    policy: ConservativeDecisionPolicy = DEPLOYED_POLICY
    id_factory: Callable[[], str] = lambda: str(uuid4())
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def decide(self, context: DecisionContext, key: str) -> DecisionResult:
        request_fingerprint = fingerprint(context)
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
                evaluation = self.rules.evaluate(context)
                decision = self.policy.decide(
                    evaluation, decision_id=decision_id, decided_at=self.clock()
                )
                repository.record(DecisionRecord(context, evaluation, decision))
                result = DecisionResult(decision, replayed=False)
        # Exiting engine.begin commits; commit errors cannot yield HTTP success.
        return result
