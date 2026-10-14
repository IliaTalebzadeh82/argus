"""Explicit mapping between immutable snapshots and relational audit rows."""

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from argus.domain.models import (
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
from argus.fraud.rules import (
    IndeterminateDiagnostic,
    RuleEvaluation,
    RuleEvaluationStatus,
    RuleSetEvaluation,
)
from argus.persistence import schema as s
from argus.persistence.records import DecisionRecord


class PersistenceConflict(ValueError):
    """An identity already names a different immutable fact or decision."""


def _signal_row(signal: RiskSignal) -> dict:
    return {
        "code": signal.code,
        "value_type": type(signal.value).__name__,
        "value": signal.value,
        "observed_at": signal.observed_at,
        "source": signal.source,
    }


def _signal_from_row(row) -> RiskSignal:
    value = row.value
    types = {"bool": bool, "int": int, "float": float, "str": str}
    expected = types[row.value_type]
    if type(value) is not expected:
        raise ValueError("stored signal scalar type differs from value_type")
    return RiskSignal(
        code=row.code, value=value, observed_at=row.observed_at, source=row.source
    )


def _ordered(connection: Connection, table, decision_id: str, *columns):
    return connection.execute(
        select(table)
        .where(table.c.decision_id == decision_id)
        .order_by(*(table.c[column] for column in columns))
    ).all()


class PostgresDecisionRepository:
    """Caller owns the transaction; use with engine.begin()."""

    def __init__(self, connection: Connection):
        self.connection = connection

    def _reuse_fact(self, table, key: str, values: dict) -> None:
        self.connection.execute(insert(table).values(**values).on_conflict_do_nothing())
        row = (
            self.connection.execute(select(table).where(table.c[key] == values[key]))
            .one()
            ._mapping
        )
        for column, expected in values.items():
            actual = row[column]
            if hasattr(actual, "astimezone"):
                actual = actual.astimezone(UTC)
            if actual != expected or type(actual) is not type(expected):
                raise PersistenceConflict(
                    f"conflicting {table.name}.{key}: {values[key]}"
                )

    def record(self, record: DecisionRecord) -> None:
        if not isinstance(record, DecisionRecord):
            raise TypeError("record must be a DecisionRecord")
        c = self.connection
        if not c.in_transaction():
            raise RuntimeError("record requires a caller-owned transaction")
        context = record.context
        decision = record.decision
        if c.execute(
            select(s.decisions.c.decision_id).where(
                s.decisions.c.decision_id == decision.decision_id
            )
        ).first():
            raise PersistenceConflict(
                f"decision already exists: {decision.decision_id}"
            )
        user = context.user
        transaction = context.transaction
        payment = context.payment_attempt
        self._reuse_fact(s.users, "user_id", user.model_dump())
        for device in context.devices:
            self._reuse_fact(s.devices, "device_id", device.model_dump())
        self._reuse_fact(
            s.transactions,
            "transaction_id",
            {
                "transaction_id": transaction.transaction_id,
                "user_id": transaction.user_id,
                "merchant_id": transaction.merchant_id,
                "amount_minor": transaction.amount.amount_minor,
                "currency": transaction.amount.currency,
                "created_at": transaction.created_at,
            },
        )
        self._reuse_fact(s.payments, "payment_id", payment.model_dump())
        c.execute(
            s.decisions.insert().values(
                decision_id=decision.decision_id,
                subject_id=decision.subject_id,
                payment_id=payment.payment_id,
                action=decision.action.value,
                decided_at=decision.decided_at,
                policy_id=decision.policy_id,
                policy_version=decision.policy_version,
                rule_set_id=decision.rule_set_id,
                rule_set_version=decision.rule_set_version,
            )
        )
        for ordinal, reason in enumerate(decision.reason_codes):
            c.execute(
                s.reasons.insert().values(
                    decision_id=decision.decision_id,
                    ordinal=ordinal,
                    reason_code=reason,
                )
            )
        for ordinal, device in enumerate(context.devices):
            c.execute(
                s.decision_devices.insert().values(
                    decision_id=decision.decision_id,
                    ordinal=ordinal,
                    device_id=device.device_id,
                )
            )
        for ordinal, signal in enumerate(context.risk_signals):
            c.execute(
                s.signals.insert().values(
                    decision_id=decision.decision_id,
                    ordinal=ordinal,
                    **_signal_row(signal),
                )
            )
        for ordinal, evaluation in enumerate(record.rule_set_evaluation.evaluations):
            c.execute(
                s.evaluations.insert().values(
                    decision_id=decision.decision_id,
                    ordinal=ordinal,
                    rule_id=evaluation.rule_id,
                    rule_version=evaluation.rule_version,
                    status=evaluation.status.value,
                    recommended_action=(
                        evaluation.recommended_action.value
                        if evaluation.recommended_action
                        else None
                    ),
                    reason_code=evaluation.reason_code,
                    diagnostic=evaluation.diagnostic.value
                    if evaluation.diagnostic
                    else None,
                )
            )
            for evidence_ordinal, signal in enumerate(evaluation.evidence):
                c.execute(
                    s.evidence.insert().values(
                        decision_id=decision.decision_id,
                        evaluation_ordinal=ordinal,
                        evidence_ordinal=evidence_ordinal,
                        **_signal_row(signal),
                    )
                )

    def get(self, decision_id: str) -> DecisionRecord | None:
        c = self.connection
        decision_row = c.execute(
            select(s.decisions).where(s.decisions.c.decision_id == decision_id)
        ).first()
        if decision_row is None:
            return None
        d = decision_row._mapping
        t = (
            c.execute(
                select(s.transactions).where(
                    s.transactions.c.transaction_id == d["subject_id"]
                )
            )
            .one()
            ._mapping
        )
        u = (
            c.execute(select(s.users).where(s.users.c.user_id == t["user_id"]))
            .one()
            ._mapping
        )
        p = (
            c.execute(
                select(s.payments).where(s.payments.c.payment_id == d["payment_id"])
            )
            .one()
            ._mapping
        )
        device_rows = _ordered(c, s.decision_devices, decision_id, "ordinal")
        device_ids = [row.device_id for row in device_rows]
        devices = tuple(
            Device(
                **c.execute(select(s.devices).where(s.devices.c.device_id == device_id))
                .one()
                ._mapping
            )
            for device_id in device_ids
        )
        context = DecisionContext(
            user=UserAccount(**u),
            transaction=Transaction(
                transaction_id=t["transaction_id"],
                user_id=t["user_id"],
                merchant_id=t["merchant_id"],
                amount=Money(amount_minor=t["amount_minor"], currency=t["currency"]),
                created_at=t["created_at"],
            ),
            payment_attempt=PaymentAttempt(**p),
            devices=devices,
            risk_signals=tuple(
                _signal_from_row(row)
                for row in _ordered(c, s.signals, decision_id, "ordinal")
            ),
        )
        evaluations = []
        for row in _ordered(c, s.evaluations, decision_id, "ordinal"):
            evidence_rows = c.execute(
                select(s.evidence)
                .where(
                    s.evidence.c.decision_id == decision_id,
                    s.evidence.c.evaluation_ordinal == row.ordinal,
                )
                .order_by(s.evidence.c.evidence_ordinal)
            ).all()
            evaluations.append(
                RuleEvaluation(
                    rule_id=row.rule_id,
                    rule_version=row.rule_version,
                    status=RuleEvaluationStatus(row.status),
                    recommended_action=(
                        DecisionAction(row.recommended_action)
                        if row.recommended_action
                        else None
                    ),
                    reason_code=row.reason_code,
                    diagnostic=(
                        IndeterminateDiagnostic(row.diagnostic)
                        if row.diagnostic
                        else None
                    ),
                    evidence=tuple(_signal_from_row(item) for item in evidence_rows),
                )
            )
        result = RuleSetEvaluation(
            rule_set_id=d["rule_set_id"],
            rule_set_version=d["rule_set_version"],
            subject_id=d["subject_id"],
            evaluations=tuple(evaluations),
        )
        decision = Decision(
            decision_id=d["decision_id"],
            subject_id=d["subject_id"],
            action=d["action"],
            decided_at=d["decided_at"],
            reason_codes=tuple(
                row.reason_code
                for row in _ordered(c, s.reasons, decision_id, "ordinal")
            ),
            policy_id=d["policy_id"],
            policy_version=d["policy_version"],
            rule_set_id=d["rule_set_id"],
            rule_set_version=d["rule_set_version"],
        )
        return DecisionRecord(context, result, decision)
