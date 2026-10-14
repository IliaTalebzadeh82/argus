"""DecisionRecord coherence without a database."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from argus.domain.models import (
    Decision,
    DecisionAction,
    DecisionContext,
    Money,
    PaymentAttempt,
    Transaction,
    UserAccount,
)
from argus.fraud.rules import (
    IndeterminateDiagnostic,
    RuleEvaluation,
    RuleEvaluationStatus,
    RuleSetEvaluation,
)
from argus.persistence.records import DecisionRecord

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def coherent():
    context = DecisionContext(
        user=UserAccount(user_id="user", created_at=NOW),
        transaction=Transaction(
            transaction_id="transaction",
            user_id="user",
            merchant_id="merchant",
            amount=Money(amount_minor=1, currency="USD"),
            created_at=NOW,
        ),
        payment_attempt=PaymentAttempt(
            payment_id="payment", transaction_id="transaction", attempted_at=NOW
        ),
    )
    result = RuleSetEvaluation(
        "rules",
        1,
        "transaction",
        (
            RuleEvaluation(
                "rule",
                1,
                RuleEvaluationStatus.INDETERMINATE,
                diagnostic=IndeterminateDiagnostic.MISSING_SIGNAL,
            ),
        ),
    )
    decision = Decision(
        decision_id="decision",
        subject_id="transaction",
        action=DecisionAction.REVIEW,
        decided_at=NOW,
        reason_codes=("RULE_EVALUATION_INDETERMINATE",),
        policy_id="policy",
        policy_version=1,
        rule_set_id="rules",
        rule_set_version=1,
    )
    return DecisionRecord(context, result, decision)


def test_coherent_record():
    assert coherent().decision.subject_id == "transaction"


def test_rejects_subject_mismatch():
    record = coherent()
    with pytest.raises(ValueError, match="subject"):
        replace(
            record, decision=record.decision.model_copy(update={"subject_id": "other"})
        )


def test_rejects_rule_set_mismatch():
    record = coherent()
    with pytest.raises(ValueError, match="rule set"):
        replace(
            record, decision=record.decision.model_copy(update={"rule_set_version": 2})
        )
