from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from argus.domain.models import (
    DecisionAction,
    DecisionContext,
    Money,
    PaymentAttempt,
    RiskSignal,
    Transaction,
    UserAccount,
)
from argus.fraud import (
    FailedPaymentVelocityRule,
    IndeterminateDiagnostic,
    PaymentVelocityRule,
    RuleEngine,
    RuleEvaluation,
    RuleEvaluationStatus,
    SharedDeviceAccountsRule,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
SOURCE = "velocity_features"
RULES = (
    (
        PaymentVelocityRule,
        "payments_10m",
        DecisionAction.CHALLENGE,
        "PAYMENT_VELOCITY_HIGH",
    ),
    (
        SharedDeviceAccountsRule,
        "accounts_on_device",
        DecisionAction.REVIEW,
        "DEVICE_SHARED_ACROSS_ACCOUNTS",
    ),
    (
        FailedPaymentVelocityRule,
        "failed_payments_1h",
        DecisionAction.REVIEW,
        "FAILED_PAYMENT_VELOCITY_HIGH",
    ),
)


def signal(
    code: str, value: bool | int | float | str, source: str = SOURCE
) -> RiskSignal:
    return RiskSignal(code=code, value=value, source=source, observed_at=NOW)


def context(*signals: RiskSignal) -> DecisionContext:
    return DecisionContext(
        user=UserAccount(user_id="user-1", created_at=NOW),
        transaction=Transaction(
            transaction_id="txn-1",
            user_id="user-1",
            merchant_id="merchant-1",
            amount=Money(amount_minor=100, currency="USD"),
            created_at=NOW,
        ),
        payment_attempt=PaymentAttempt(
            payment_id="pay-1", transaction_id="txn-1", attempted_at=NOW
        ),
        risk_signals=signals,
    )


@pytest.mark.parametrize("rule_type,code,action,reason", RULES)
def test_matches_at_threshold_with_exact_evidence(
    rule_type, code, action, reason
) -> None:
    evidence = signal(code, 5)
    result = rule_type(threshold=5, source=SOURCE).evaluate(context(evidence))
    assert result.status is RuleEvaluationStatus.MATCHED
    assert result.recommended_action is action
    assert result.reason_code == reason
    assert result.evidence == (evidence,)
    assert result.evidence[0] is evidence
    assert result.diagnostic is None


@pytest.mark.parametrize("rule_type,code,action,reason", RULES)
def test_below_threshold_is_not_matched(rule_type, code, action, reason) -> None:
    evidence = signal(code, 4)
    result = rule_type(threshold=5, source=SOURCE).evaluate(context(evidence))
    assert result.status is RuleEvaluationStatus.NOT_MATCHED
    assert result.evidence == (evidence,)
    assert result.recommended_action is None
    assert result.reason_code is None


@pytest.mark.parametrize("rule_type,code,action,reason", RULES)
def test_missing_signal_is_indeterminate(rule_type, code, action, reason) -> None:
    result = rule_type(threshold=5, source=SOURCE).evaluate(context())
    assert result.status is RuleEvaluationStatus.INDETERMINATE
    assert result.diagnostic is IndeterminateDiagnostic.MISSING_SIGNAL
    assert result.recommended_action is None
    assert result.evidence == ()


def test_wrong_source_is_missing_and_other_source_does_not_duplicate() -> None:
    rule = PaymentVelocityRule(threshold=5, source=SOURCE)
    other = signal("payments_10m", 50, source="another_source")
    assert (
        rule.evaluate(context(other)).diagnostic
        is IndeterminateDiagnostic.MISSING_SIGNAL
    )
    expected = signal("payments_10m", 5)
    assert rule.evaluate(context(other, expected)).evidence == (expected,)


def test_duplicate_exact_signal_is_ambiguous() -> None:
    rule = PaymentVelocityRule(threshold=5, source=SOURCE)
    result = rule.evaluate(
        context(signal("payments_10m", 5), signal("payments_10m", 6))
    )
    assert result.status is RuleEvaluationStatus.INDETERMINATE
    assert result.diagnostic is IndeterminateDiagnostic.AMBIGUOUS_SIGNAL


@pytest.mark.parametrize("value", [True, 3.0, "3"])
@pytest.mark.parametrize("rule_type,code,action,reason", RULES)
def test_wrong_scalar_type_is_indeterminate(
    rule_type, code, action, reason, value
) -> None:
    result = rule_type(threshold=5, source=SOURCE).evaluate(
        context(signal(code, value))
    )
    assert result.status is RuleEvaluationStatus.INDETERMINATE
    assert result.diagnostic is IndeterminateDiagnostic.INVALID_SIGNAL_TYPE


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": RuleEvaluationStatus.MATCHED},
        {
            "status": RuleEvaluationStatus.NOT_MATCHED,
            "recommended_action": DecisionAction.REVIEW,
        },
        {
            "status": RuleEvaluationStatus.INDETERMINATE,
            "recommended_action": DecisionAction.REVIEW,
        },
        {"status": RuleEvaluationStatus.INDETERMINATE},
        {"status": RuleEvaluationStatus.MATCHED, "reason_code": "HIGH"},
        {
            "status": RuleEvaluationStatus.MATCHED,
            "recommended_action": DecisionAction.REVIEW,
            "reason_code": "human prose",
            "evidence": (signal("payments_10m", 5),),
        },
        {"status": RuleEvaluationStatus.NOT_MATCHED, "reason_code": "HIGH"},
        {"status": RuleEvaluationStatus.INDETERMINATE, "reason_code": "HIGH"},
    ],
)
def test_evaluation_rejects_incoherent_results(kwargs) -> None:
    with pytest.raises(ValueError):
        RuleEvaluation(rule_id="rule", rule_version=1, **kwargs)


def test_evaluation_is_immutable() -> None:
    result = PaymentVelocityRule(threshold=5, source=SOURCE).evaluate(
        context(signal("payments_10m", 5))
    )
    with pytest.raises(FrozenInstanceError):
        result.status = RuleEvaluationStatus.NOT_MATCHED


@pytest.mark.parametrize("threshold", [0, -1, True, 3.0, "3"])
def test_bad_threshold_rejected(threshold) -> None:
    with pytest.raises(ValueError):
        PaymentVelocityRule(threshold=threshold, source=SOURCE)


@pytest.mark.parametrize("source", ["", "   "])
def test_empty_source_rejected(source) -> None:
    with pytest.raises(ValueError):
        PaymentVelocityRule(threshold=5, source=source)


@pytest.mark.parametrize("version", [0, -1, True])
def test_bad_rule_version_rejected(version) -> None:
    with pytest.raises(ValueError):
        PaymentVelocityRule(threshold=5, source=SOURCE, rule_version=version)


def test_engine_evaluates_all_in_order_preserving_conflicts_and_is_repeatable() -> None:
    rules = (
        PaymentVelocityRule(threshold=5, source=SOURCE),
        SharedDeviceAccountsRule(threshold=5, source=SOURCE),
        FailedPaymentVelocityRule(threshold=5, source=SOURCE),
    )
    engine = RuleEngine(rules, "core_fraud", 1)
    facts = context(
        signal("payments_10m", 5),
        signal("accounts_on_device", 6),
        signal("failed_payments_1h", 4),
    )
    results = engine.evaluate(facts)
    assert results.rule_set_id == "core_fraud"
    assert results.rule_set_version == 1
    assert results.subject_id == "txn-1"
    assert isinstance(results.evaluations, tuple)
    assert [item.rule_id for item in results.evaluations] == [
        rule.rule_id for rule in rules
    ]
    assert [item.status for item in results.evaluations] == [
        RuleEvaluationStatus.MATCHED,
        RuleEvaluationStatus.MATCHED,
        RuleEvaluationStatus.NOT_MATCHED,
    ]
    assert [item.recommended_action for item in results.evaluations] == [
        DecisionAction.CHALLENGE,
        DecisionAction.REVIEW,
        None,
    ]
    assert engine.evaluate(facts) == results


def test_engine_rejects_duplicate_rule_identity_but_allows_other_version() -> None:
    rule = PaymentVelocityRule(threshold=5, source=SOURCE)
    with pytest.raises(ValueError, match="duplicate rule identity"):
        RuleEngine((rule, PaymentVelocityRule(threshold=10, source=SOURCE)), "core", 1)
    RuleEngine(
        (rule, PaymentVelocityRule(threshold=10, source=SOURCE, rule_version=2)),
        "core",
        1,
    )
