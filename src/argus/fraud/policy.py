"""Deterministic composition of completed rule evaluations."""

from dataclasses import dataclass
from datetime import datetime
from re import fullmatch
from typing import ClassVar, Protocol

from argus.domain.models import Decision, DecisionAction
from argus.fraud.rules import RuleEvaluationStatus, RuleSetEvaluation

NO_RISK_RULE_MATCHED = "NO_RISK_RULE_MATCHED"
RULE_EVALUATION_INDETERMINATE = "RULE_EVALUATION_INDETERMINATE"


class DecisionPolicy(Protocol):
    policy_id: str
    policy_version: int

    def decide(
        self,
        result: RuleSetEvaluation,
        *,
        decision_id: str,
        decided_at: datetime,
    ) -> Decision: ...


@dataclass(frozen=True)
class ConservativeDecisionPolicy:
    """Phase-1 demonstration policy; published behavior requires a version bump."""

    policy_version: int = 1
    policy_id: ClassVar[str] = "conservative_fraud"

    def __post_init__(self) -> None:
        if not fullmatch(r"[a-z][a-z0-9_]*", self.policy_id):
            raise ValueError("policy_id must be a machine-readable code")
        if type(self.policy_version) is not int or self.policy_version <= 0:
            raise ValueError("policy_version must be a positive integer")

    def decide(
        self,
        result: RuleSetEvaluation,
        *,
        decision_id: str,
        decided_at: datetime,
    ) -> Decision:
        if not isinstance(result, RuleSetEvaluation):
            raise TypeError("result must be a RuleSetEvaluation")

        matched = tuple(
            item
            for item in result.evaluations
            if item.status is RuleEvaluationStatus.MATCHED
        )
        actions = {item.recommended_action for item in matched}
        indeterminate = any(
            item.status is RuleEvaluationStatus.INDETERMINATE
            for item in result.evaluations
        )

        if DecisionAction.BLOCK in actions:
            action = DecisionAction.BLOCK
        elif indeterminate or DecisionAction.REVIEW in actions:
            action = DecisionAction.REVIEW
        elif DecisionAction.CHALLENGE in actions:
            action = DecisionAction.CHALLENGE
        else:
            action = DecisionAction.ALLOW

        reasons = [item.reason_code for item in matched]
        if indeterminate and action is not DecisionAction.BLOCK:
            reasons.append(RULE_EVALUATION_INDETERMINATE)
        elif not matched and not indeterminate:
            reasons.append(NO_RISK_RULE_MATCHED)

        return Decision(
            decision_id=decision_id,
            subject_id=result.subject_id,
            action=action,
            decided_at=decided_at,
            reason_codes=tuple(dict.fromkeys(reasons)),
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            rule_set_id=result.rule_set_id,
            rule_set_version=result.rule_set_version,
        )
