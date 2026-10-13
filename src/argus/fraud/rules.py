"""Rules interpret supplied facts; policy later composes their recommendations."""

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import ClassVar, Protocol

from argus.domain.models import DecisionAction, DecisionContext, RiskSignal


class RuleEvaluationStatus(StrEnum):
    MATCHED = "MATCHED"
    NOT_MATCHED = "NOT_MATCHED"
    INDETERMINATE = "INDETERMINATE"


class IndeterminateDiagnostic(StrEnum):
    MISSING_SIGNAL = "MISSING_SIGNAL"
    AMBIGUOUS_SIGNAL = "AMBIGUOUS_SIGNAL"
    INVALID_SIGNAL_TYPE = "INVALID_SIGNAL_TYPE"


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    rule_version: int
    status: RuleEvaluationStatus
    recommended_action: DecisionAction | None = None
    reason_code: str | None = None
    evidence: tuple[RiskSignal, ...] = ()
    diagnostic: IndeterminateDiagnostic | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or not fullmatch(
            r"[a-z][a-z0-9_]*", self.rule_id
        ):
            raise ValueError("rule_id must be a machine-readable code")
        if type(self.rule_version) is not int or self.rule_version <= 0:
            raise ValueError("rule_version must be a positive integer")
        if not isinstance(self.status, RuleEvaluationStatus):
            raise ValueError("status must be a RuleEvaluationStatus")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, RiskSignal) for item in self.evidence
        ):
            raise ValueError("evidence must be a tuple of RiskSignals")
        if self.status is RuleEvaluationStatus.MATCHED:
            if (
                not isinstance(self.recommended_action, DecisionAction)
                or not isinstance(self.reason_code, str)
                or not fullmatch(r"[A-Z][A-Z0-9_]*", self.reason_code)
                or not self.evidence
                or self.diagnostic is not None
            ):
                raise ValueError(
                    "matched evaluation requires action, reason, and evidence"
                )
        elif self.status is RuleEvaluationStatus.NOT_MATCHED:
            if any(
                value is not None
                for value in (
                    self.recommended_action,
                    self.reason_code,
                    self.diagnostic,
                )
            ):
                raise ValueError("not-matched evaluation cannot recommend or diagnose")
        elif (
            not isinstance(self.diagnostic, IndeterminateDiagnostic)
            or self.recommended_action is not None
            or self.reason_code is not None
            or self.evidence
        ):
            raise ValueError("indeterminate evaluation requires only a diagnostic")


@dataclass(frozen=True)
class RuleSetEvaluation:
    rule_set_id: str
    rule_set_version: int
    subject_id: str
    evaluations: tuple[RuleEvaluation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rule_set_id, str) or not fullmatch(
            r"[a-z][a-z0-9_]*", self.rule_set_id
        ):
            raise ValueError("rule_set_id must be a machine-readable code")
        if type(self.rule_set_version) is not int or self.rule_set_version <= 0:
            raise ValueError("rule_set_version must be a positive integer")
        if not isinstance(self.subject_id, str) or not self.subject_id.strip():
            raise ValueError("subject_id must be non-empty")
        if not isinstance(self.evaluations, tuple) or not self.evaluations:
            raise ValueError("evaluations must be a non-empty tuple")
        identities: set[tuple[str, int]] = set()
        for evaluation in self.evaluations:
            if not isinstance(evaluation, RuleEvaluation):
                raise ValueError("evaluations must contain RuleEvaluations")
            identity = (evaluation.rule_id, evaluation.rule_version)
            if identity in identities:
                raise ValueError(f"duplicate rule identity: {identity}")
            identities.add(identity)


class Rule(Protocol):
    rule_id: str
    rule_version: int

    def evaluate(self, context: DecisionContext) -> RuleEvaluation: ...


@dataclass(frozen=True)
class _IntegerCountRule:
    threshold: int
    source: str
    rule_version: int = 1

    rule_id: ClassVar[str]
    signal_code: ClassVar[str]
    action: ClassVar[DecisionAction]
    reason: ClassVar[str]

    def __post_init__(self) -> None:
        if type(self.threshold) is not int or self.threshold <= 0:
            raise ValueError("threshold must be a positive integer")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be non-empty")
        if type(self.rule_version) is not int or self.rule_version <= 0:
            raise ValueError("rule_version must be a positive integer")

    def evaluate(self, context: DecisionContext) -> RuleEvaluation:
        signals = tuple(
            signal
            for signal in context.risk_signals
            if signal.code == self.signal_code and signal.source == self.source
        )
        if not signals:
            return RuleEvaluation(
                self.rule_id,
                self.rule_version,
                RuleEvaluationStatus.INDETERMINATE,
                diagnostic=IndeterminateDiagnostic.MISSING_SIGNAL,
            )
        if len(signals) > 1:
            return RuleEvaluation(
                self.rule_id,
                self.rule_version,
                RuleEvaluationStatus.INDETERMINATE,
                diagnostic=IndeterminateDiagnostic.AMBIGUOUS_SIGNAL,
            )
        signal = signals[0]
        if type(signal.value) is not int:
            return RuleEvaluation(
                self.rule_id,
                self.rule_version,
                RuleEvaluationStatus.INDETERMINATE,
                diagnostic=IndeterminateDiagnostic.INVALID_SIGNAL_TYPE,
            )
        if signal.value >= self.threshold:
            return RuleEvaluation(
                self.rule_id,
                self.rule_version,
                RuleEvaluationStatus.MATCHED,
                recommended_action=self.action,
                reason_code=self.reason,
                evidence=(signal,),
            )
        return RuleEvaluation(
            self.rule_id,
            self.rule_version,
            RuleEvaluationStatus.NOT_MATCHED,
            evidence=(signal,),
        )


class PaymentVelocityRule(_IntegerCountRule):
    rule_id = "payment_velocity_10m"
    signal_code = "payments_10m"
    action = DecisionAction.CHALLENGE
    reason = "PAYMENT_VELOCITY_HIGH"


class SharedDeviceAccountsRule(_IntegerCountRule):
    rule_id = "shared_device_accounts"
    signal_code = "accounts_on_device"
    action = DecisionAction.REVIEW
    reason = "DEVICE_SHARED_ACROSS_ACCOUNTS"


class FailedPaymentVelocityRule(_IntegerCountRule):
    rule_id = "failed_payment_velocity_1h"
    signal_code = "failed_payments_1h"
    action = DecisionAction.REVIEW
    reason = "FAILED_PAYMENT_VELOCITY_HIGH"


@dataclass(frozen=True)
class RuleEngine:
    rules: tuple[Rule, ...]
    rule_set_id: str
    rule_set_version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))
        if not isinstance(self.rule_set_id, str) or not fullmatch(
            r"[a-z][a-z0-9_]*", self.rule_set_id
        ):
            raise ValueError("rule_set_id must be a machine-readable code")
        if type(self.rule_set_version) is not int or self.rule_set_version <= 0:
            raise ValueError("rule_set_version must be a positive integer")
        if not self.rules:
            raise ValueError("rule set must contain at least one rule")
        identities: set[tuple[str, int]] = set()
        for rule in self.rules:
            if not isinstance(rule.rule_id, str) or not fullmatch(
                r"[a-z][a-z0-9_]*", rule.rule_id
            ):
                raise ValueError("rule_id must be a machine-readable code")
            if type(rule.rule_version) is not int or rule.rule_version <= 0:
                raise ValueError("rule_version must be a positive integer")
            identity = (rule.rule_id, rule.rule_version)
            if identity in identities:
                raise ValueError(f"duplicate rule identity: {identity}")
            identities.add(identity)

    def evaluate(self, context: DecisionContext) -> RuleSetEvaluation:
        evaluations = tuple(rule.evaluate(context) for rule in self.rules)
        for rule, evaluation in zip(self.rules, evaluations, strict=True):
            if (rule.rule_id, rule.rule_version) != (
                evaluation.rule_id,
                evaluation.rule_version,
            ):
                raise ValueError("rule evaluation identity does not match registration")
        return RuleSetEvaluation(
            rule_set_id=self.rule_set_id,
            rule_set_version=self.rule_set_version,
            subject_id=context.transaction.transaction_id,
            evaluations=evaluations,
        )
