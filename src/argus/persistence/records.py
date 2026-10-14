"""One coherent, immutable deterministic audit record."""

from dataclasses import dataclass

from argus.domain.models import Decision, DecisionContext
from argus.fraud.rules import RuleSetEvaluation


@dataclass(frozen=True)
class DecisionRecord:
    context: DecisionContext
    rule_set_evaluation: RuleSetEvaluation
    decision: Decision

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context, DecisionContext)
            or not isinstance(self.rule_set_evaluation, RuleSetEvaluation)
            or not isinstance(self.decision, Decision)
        ):
            raise ValueError("record requires context, evaluation, and decision")
        if not (
            self.decision.subject_id
            == self.rule_set_evaluation.subject_id
            == self.context.transaction.transaction_id
        ):
            raise ValueError("decision subject does not match evaluation/context")
        if (
            self.decision.rule_set_id,
            self.decision.rule_set_version,
        ) != (
            self.rule_set_evaluation.rule_set_id,
            self.rule_set_evaluation.rule_set_version,
        ):
            raise ValueError("decision rule set does not match evaluation")
