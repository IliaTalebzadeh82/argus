"""Real PostgreSQL audit persistence tests; run explicitly with test-integration."""

import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

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
from argus.persistence.database import create_engine
from argus.persistence.records import DecisionRecord
from argus.persistence.repository import PersistenceConflict, PostgresDecisionRepository

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def sample(prefix: str) -> DecisionRecord:
    signals = (
        RiskSignal(code="flag", value=True, observed_at=NOW, source="test"),
        RiskSignal(code="count", value=3, observed_at=NOW, source="test"),
        RiskSignal(code="ratio", value=3.25, observed_at=NOW, source="test"),
        RiskSignal(code="label", value="watch", observed_at=NOW, source="test"),
    )
    context = DecisionContext(
        user=UserAccount(user_id=f"{prefix}-user", created_at=NOW),
        transaction=Transaction(
            transaction_id=f"{prefix}-transaction",
            user_id=f"{prefix}-user",
            merchant_id="merchant",
            amount=Money(amount_minor=100, currency="usd"),
            created_at=NOW,
        ),
        payment_attempt=PaymentAttempt(
            payment_id=f"{prefix}-payment",
            transaction_id=f"{prefix}-transaction",
            attempted_at=NOW,
        ),
        devices=(
            Device(device_id=f"{prefix}-device-2", first_seen_at=NOW),
            Device(device_id=f"{prefix}-device-1", first_seen_at=NOW),
        ),
        risk_signals=signals,
    )
    result = RuleSetEvaluation(
        rule_set_id="rules",
        rule_set_version=2,
        subject_id=context.transaction.transaction_id,
        evaluations=(
            RuleEvaluation(
                "first",
                1,
                RuleEvaluationStatus.MATCHED,
                recommended_action=DecisionAction.REVIEW,
                reason_code="FIRST",
                evidence=(signals[1], signals[0]),
            ),
            RuleEvaluation(
                "second", 1, RuleEvaluationStatus.NOT_MATCHED, evidence=(signals[2],)
            ),
            RuleEvaluation(
                "third",
                1,
                RuleEvaluationStatus.MATCHED,
                recommended_action=DecisionAction.BLOCK,
                reason_code="THIRD",
                evidence=(signals[3],),
            ),
            RuleEvaluation(
                "fourth",
                1,
                RuleEvaluationStatus.INDETERMINATE,
                diagnostic=IndeterminateDiagnostic.MISSING_SIGNAL,
            ),
        ),
    )
    decision = Decision(
        decision_id=f"{prefix}-decision",
        subject_id=context.transaction.transaction_id,
        action=DecisionAction.BLOCK,
        decided_at=NOW,
        reason_codes=("FIRST", "THIRD"),
        policy_id="policy",
        policy_version=1,
        rule_set_id="rules",
        rule_set_version=2,
    )
    return DecisionRecord(context, result, decision)


@pytest.fixture
def connection():
    url = os.environ["ARGUS_DATABASE_URL"]
    engine = create_engine(url)
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            yield conn
        finally:
            transaction.rollback()
    engine.dispose()


def test_full_round_trip_and_orders(connection):
    record = sample(uuid4().hex)
    repo = PostgresDecisionRepository(connection)
    assert repo.get(record.decision.decision_id) is None
    repo.record(record)
    restored = PostgresDecisionRepository(connection).get(record.decision.decision_id)
    assert restored == record
    assert [type(x.value) for x in restored.context.risk_signals] == [
        bool,
        int,
        float,
        str,
    ]
    assert tuple(x.device_id for x in restored.context.devices) == tuple(
        x.device_id for x in record.context.devices
    )
    assert tuple(x.reason_code for x in restored.rule_set_evaluation.evaluations) == (
        "FIRST",
        None,
        "THIRD",
        None,
    )
    assert restored.rule_set_evaluation.evaluations[0].evidence == (
        record.context.risk_signals[1],
        record.context.risk_signals[0],
    )
    assert restored.decision.reason_codes == ("FIRST", "THIRD")


def test_reuse_shared_facts_and_multiple_payments(connection):
    first = sample(uuid4().hex)
    repo = PostgresDecisionRepository(connection)
    repo.record(first)
    second_context = first.context.model_copy(
        update={
            "payment_attempt": PaymentAttempt(
                payment_id=f"{uuid4().hex}-payment",
                transaction_id=first.context.transaction.transaction_id,
                attempted_at=NOW,
            )
        }
    )
    second = DecisionRecord(
        second_context,
        first.rule_set_evaluation,
        first.decision.model_copy(update={"decision_id": f"{uuid4().hex}-decision"}),
    )
    repo.record(second)
    assert repo.get(second.decision.decision_id) == second
    assert (
        connection.execute(
            select(s.payments).where(
                s.payments.c.transaction_id == first.context.transaction.transaction_id
            )
        )
        .fetchall()
        .__len__()
        == 2
    )
    with pytest.raises(PersistenceConflict, match="decision already exists"):
        repo.record(first)


def test_conflicting_immutable_fact_rolls_back_earlier_inserts(connection):
    first = sample(uuid4().hex)
    repo = PostgresDecisionRepository(connection)
    repo.record(first)
    transaction = connection.begin_nested()
    conflict = sample(uuid4().hex)
    conflicting_context = conflict.context.model_copy(
        update={
            "transaction": first.context.transaction.model_copy(
                update={
                    "user_id": conflict.context.user.user_id,
                    "amount": Money(amount_minor=999, currency="USD"),
                }
            ),
            "payment_attempt": conflict.context.payment_attempt.model_copy(
                update={"transaction_id": first.context.transaction.transaction_id}
            ),
        }
    )
    conflicting_result = replace(
        conflict.rule_set_evaluation,
        subject_id=first.context.transaction.transaction_id,
    )
    conflicting_decision = conflict.decision.model_copy(
        update={"subject_id": first.context.transaction.transaction_id}
    )
    with pytest.raises(PersistenceConflict, match="conflicting transactions"):
        repo.record(
            DecisionRecord(
                conflicting_context, conflicting_result, conflicting_decision
            )
        )
    transaction.rollback()
    assert (
        connection.execute(
            select(s.users).where(s.users.c.user_id == conflict.context.user.user_id)
        ).first()
        is None
    )
    assert repo.get(conflict.decision.decision_id) is None


def test_committed_record_reconstructs_on_new_connection():
    record = sample(uuid4().hex)
    engine = create_engine(os.environ["ARGUS_DATABASE_URL"])
    try:
        with engine.begin() as writer:
            PostgresDecisionRepository(writer).record(record)
        try:
            with engine.connect() as reader:
                assert (
                    PostgresDecisionRepository(reader).get(record.decision.decision_id)
                    == record
                )
        finally:
            # Delete only the exact test identities after the committed-read check.
            with engine.begin() as cleanup:
                cleanup.execute(
                    s.decisions.delete().where(
                        s.decisions.c.decision_id == record.decision.decision_id
                    )
                )
                cleanup.execute(
                    s.payments.delete().where(
                        s.payments.c.payment_id
                        == record.context.payment_attempt.payment_id
                    )
                )
                cleanup.execute(
                    s.transactions.delete().where(
                        s.transactions.c.transaction_id
                        == record.context.transaction.transaction_id
                    )
                )
                for device in record.context.devices:
                    cleanup.execute(
                        s.devices.delete().where(
                            s.devices.c.device_id == device.device_id
                        )
                    )
                cleanup.execute(
                    s.users.delete().where(
                        s.users.c.user_id == record.context.user.user_id
                    )
                )
    finally:
        engine.dispose()
