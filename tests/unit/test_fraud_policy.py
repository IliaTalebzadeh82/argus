from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from test_fraud_rules import SOURCE, context, signal

from argus.domain.models import Decision, DecisionAction, RiskSignal
from argus.fraud import (
    ConservativeDecisionPolicy,
    IndeterminateDiagnostic,
    PaymentVelocityRule,
    RuleEngine,
    RuleEvaluation,
    RuleEvaluationStatus,
    RuleSetEvaluation,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
EVIDENCE = RiskSignal(code="synthetic", value=1, observed_at=NOW, source="test")


def matched(name: str, action: DecisionAction, reason: str) -> RuleEvaluation:
    return RuleEvaluation(
        name,
        1,
        RuleEvaluationStatus.MATCHED,
        recommended_action=action,
        reason_code=reason,
        evidence=(EVIDENCE,),
    )


def not_matched(name: str) -> RuleEvaluation:
    return RuleEvaluation(name, 1, RuleEvaluationStatus.NOT_MATCHED)


def indeterminate(name: str) -> RuleEvaluation:
    return RuleEvaluation(
        name,
        1,
        RuleEvaluationStatus.INDETERMINATE,
        diagnostic=IndeterminateDiagnostic.MISSING_SIGNAL,
    )


def result(*evaluations: RuleEvaluation) -> RuleSetEvaluation:
    return RuleSetEvaluation("core_fraud", 1, "txn-1", evaluations)


@pytest.mark.parametrize(
    "evaluations,action,reasons",
    [
        (
            (not_matched("a"), not_matched("b"), not_matched("c")),
            DecisionAction.ALLOW,
            ("NO_RISK_RULE_MATCHED",),
        ),
        (
            (matched("a", DecisionAction.CHALLENGE, "A"),),
            DecisionAction.CHALLENGE,
            ("A",),
        ),
        ((matched("a", DecisionAction.REVIEW, "A"),), DecisionAction.REVIEW, ("A",)),
        (
            (
                matched("a", DecisionAction.CHALLENGE, "A"),
                matched("b", DecisionAction.REVIEW, "B"),
            ),
            DecisionAction.REVIEW,
            ("A", "B"),
        ),
        (
            (indeterminate("a"),),
            DecisionAction.REVIEW,
            ("RULE_EVALUATION_INDETERMINATE",),
        ),
        (
            (matched("a", DecisionAction.CHALLENGE, "A"), indeterminate("b")),
            DecisionAction.REVIEW,
            ("A", "RULE_EVALUATION_INDETERMINATE"),
        ),
        (
            (matched("a", DecisionAction.BLOCK, "A"), indeterminate("b")),
            DecisionAction.BLOCK,
            ("A",),
        ),
        (
            (
                matched("a", DecisionAction.BLOCK, "A"),
                matched("b", DecisionAction.REVIEW, "B"),
                matched("c", DecisionAction.CHALLENGE, "C"),
            ),
            DecisionAction.BLOCK,
            ("A", "B", "C"),
        ),
        ((matched("a", DecisionAction.ALLOW, "A"),), DecisionAction.ALLOW, ("A",)),
        (
            (matched("a", DecisionAction.ALLOW, "A"), indeterminate("b")),
            DecisionAction.REVIEW,
            ("A", "RULE_EVALUATION_INDETERMINATE"),
        ),
        (
            (
                matched("a", DecisionAction.REVIEW, "SAME"),
                matched("b", DecisionAction.CHALLENGE, "SAME"),
                matched("c", DecisionAction.CHALLENGE, "OTHER"),
            ),
            DecisionAction.REVIEW,
            ("SAME", "OTHER"),
        ),
    ],
)
def test_policy_matrix(evaluations, action, reasons) -> None:
    decision = ConservativeDecisionPolicy().decide(
        result(*evaluations), decision_id="decision-1", decided_at=NOW
    )
    assert decision.action is action
    assert decision.reason_codes == reasons
    assert decision.subject_id == "txn-1"
    assert decision.policy_id == "conservative_fraud"
    assert decision.policy_version == 1
    assert decision.rule_set_id == "core_fraud"
    assert decision.rule_set_version == 1


def test_repeated_inputs_produce_equal_decisions() -> None:
    evaluation = result(matched("a", DecisionAction.REVIEW, "A"))
    policy = ConservativeDecisionPolicy()
    first = policy.decide(evaluation, decision_id="d", decided_at=NOW)
    assert policy.decide(evaluation, decision_id="d", decided_at=NOW) == first
    assert Decision.model_validate_json(first.model_dump_json()) == first


def test_rule_set_configuration_version_is_distinct_from_rule_version() -> None:
    facts = context(signal("payments_10m", 7))
    first = RuleEngine((PaymentVelocityRule(5, SOURCE),), "core_fraud", 1).evaluate(
        facts
    )
    second = RuleEngine((PaymentVelocityRule(10, SOURCE),), "core_fraud", 2).evaluate(
        facts
    )
    assert first.evaluations[0].rule_version == second.evaluations[0].rule_version == 1
    assert first.evaluations[0].status is RuleEvaluationStatus.MATCHED
    assert second.evaluations[0].status is RuleEvaluationStatus.NOT_MATCHED
    assert (first.rule_set_version, second.rule_set_version) == (1, 2)
    assert first.subject_id == second.subject_id == facts.transaction.transaction_id


def test_policy_version_is_independent_of_rule_set_version() -> None:
    evaluation = result(not_matched("a"))
    first = ConservativeDecisionPolicy(1).decide(
        evaluation, decision_id="d", decided_at=NOW
    )
    second = ConservativeDecisionPolicy(2).decide(
        evaluation, decision_id="d", decided_at=NOW
    )
    assert first.policy_version == 1
    assert second.policy_version == 2
    assert first.rule_set_version == second.rule_set_version == 1


@pytest.mark.parametrize("rule_set_id", ["", "Bad ID", "123"])
def test_engine_rejects_bad_rule_set_id(rule_set_id) -> None:
    with pytest.raises(ValueError, match="rule_set_id"):
        RuleEngine((PaymentVelocityRule(5, SOURCE),), rule_set_id, 1)


@pytest.mark.parametrize("version", [0, -1, True, "1"])
def test_engine_rejects_bad_rule_set_version(version) -> None:
    with pytest.raises(ValueError, match="rule_set_version"):
        RuleEngine((PaymentVelocityRule(5, SOURCE),), "core_fraud", version)


def test_empty_rule_set_is_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="at least one rule"):
        RuleEngine((), "core_fraud", 1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rule_set_id": "Bad ID"},
        {"rule_set_version": 0},
        {"subject_id": ""},
        {"evaluations": ()},
        {"evaluations": [not_matched("a")]},
        {"evaluations": (not_matched("a"), not_matched("a"))},
    ],
)
def test_rule_set_result_rejects_bad_input(kwargs) -> None:
    fields = dict(
        rule_set_id="core_fraud",
        rule_set_version=1,
        subject_id="txn-1",
        evaluations=(not_matched("a"),),
    )
    with pytest.raises(ValueError):
        RuleSetEvaluation(**(fields | kwargs))


def test_rule_set_result_is_immutable() -> None:
    evaluation = result(not_matched("a"))
    with pytest.raises(FrozenInstanceError):
        evaluation.subject_id = "other"


@pytest.mark.parametrize("version", [0, -1, True])
def test_policy_rejects_bad_version(version) -> None:
    with pytest.raises(ValueError, match="policy_version"):
        ConservativeDecisionPolicy(version)


def test_policy_rejects_unstructured_input() -> None:
    with pytest.raises(TypeError, match="RuleSetEvaluation"):
        ConservativeDecisionPolicy().decide((), decision_id="d", decided_at=NOW)


@pytest.mark.parametrize(
    "field,value",
    [
        ("policy_id", ""),
        ("policy_id", "Bad ID"),
        ("policy_version", 0),
        ("policy_version", True),
        ("rule_set_id", ""),
        ("rule_set_id", "Bad ID"),
        ("rule_set_version", 0),
        ("rule_set_version", True),
    ],
)
def test_decision_rejects_invalid_provenance(field, value) -> None:
    fields = (
        ConservativeDecisionPolicy()
        .decide(result(not_matched("a")), decision_id="d", decided_at=NOW)
        .model_dump()
    )
    fields[field] = value
    with pytest.raises(ValidationError):
        Decision.model_validate(fields)
