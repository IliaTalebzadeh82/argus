# Deterministic fraud rules (Phase 01 / Checkpoint 02)

## Rule and policy

A rule independently evaluates one condition against a supplied `DecisionContext` and returns a `RuleEvaluation`. Its action is a recommendation. A later policy will combine all evaluations into one final action and `Decision`; this engine does not choose a winner or resolve conflicting recommendations.

## Three-state evaluation

- `MATCHED`: the required signal is present, has the expected type, and meets the threshold.
- `NOT_MATCHED`: the required signal is present and valid but falls below the threshold.
- `INDETERMINATE`: evaluation cannot complete because the signal is missing, ambiguous, or has an incompatible scalar type. The diagnostic names which case occurred.

Two states would collapse unavailable evidence into a false fraud condition. Missing evidence is not evidence of safety: an absent `payments_10m` signal never means zero payments.

## Identity and evidence

`(rule_id, rule_version)` identifies deterministic rule behavior for future reproducibility. A breaking change to a published rule definition requires a version increase; there is no registry or historical loader yet. Matched evaluations connect a machine-readable reason code to the rule identity and the exact immutable `RiskSignal` used, including its code, source, value, and observation time. A valid non-match also retains the examined signal. No natural-language evidence is authoritative.

Each rule selects by both signal code and logical source. Zero matches means missing, and multiple exact matches mean ambiguous; neither case silently selects a signal. Integer-count rules accept only actual integers, excluding booleans, floats, and strings.

## Determinism and boundary

Threshold, source, and version are explicit rule configuration. Rules read only supplied context, perform no I/O or clock reads, and generate no IDs. The engine evaluates every registered rule in registration order and returns an immutable tuple of evaluations.

CP02 has no final policy, persistence, API endpoint, Kafka, or ML. It also has no feature computation: callers supply the already-computed signals.
