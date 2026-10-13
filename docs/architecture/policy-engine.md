# Deterministic policy composition (Phase 01 / Checkpoint 03)

## Rules, rule set, and policy

A **rule** implements one condition and returns a recommendation or a diagnostic. `(rule_id, rule_version)` identifies its implementation semantics. Changing the computation or interpretation of that condition requires a rule-version bump.

A **rule set** is the deployed collection and configuration of rules. `(rule_set_id, rule_set_version)` identifies its thresholds, expected sources, enabled membership, and other behavior-affecting configuration. Changing the threshold from 5 to 10 can require a rule-set version bump while the rule implementation stays at version 1. The engine rejects empty sets and duplicate rule identities, evaluates in registration order, and returns a frozen `RuleSetEvaluation` carrying the transaction subject ID.

A **policy** combines completed evaluations into one action. `(policy_id, policy_version)` identifies its conflict resolution, uncertainty handling, reason aggregation, and fallback behavior. Any change to that behavior requires a policy-version bump. Versions are publication discipline for now; there is no registry or historical loader.

## Phase-1 demonstration policy

`ConservativeDecisionPolicy` (`conservative_fraud`, version 1) applies this project policy in order:

1. Any matched `BLOCK` recommendation yields `BLOCK`.
2. Otherwise, any `INDETERMINATE` evaluation yields `REVIEW`.
3. Otherwise, any matched `REVIEW` recommendation yields `REVIEW`.
4. Otherwise, any matched `CHALLENGE` recommendation yields `CHALLENGE`.
5. Otherwise, yield `ALLOW`.

Thus `CHALLENGE` plus uncertainty yields `REVIEW`; `BLOCK` plus uncertainty remains `BLOCK`. A matched `ALLOW` is a synthetic lowest-priority recommendation, not a production allow-list rule. The default `ALLOW` is valid only after every configured rule completed without a risk match. This ordering is an Argus demonstration policy, not a universal severity scale.

## Reason attribution

The decision preserves all matched rule reason codes in evaluation order, including reasons whose action did not win. Duplicate codes are removed at their later occurrence, preserving the first occurrence. If uncertainty is present in a non-`BLOCK` decision, `RULE_EVALUATION_INDETERMINATE` is appended. If every rule is a valid non-match, `NO_RISK_RULE_MATCHED` is appended. An indeterminate evaluation does not append an uncertainty reason when a matched `BLOCK` already determines the outcome.

The final `Decision` records the policy and rule-set identities/versions, action, and reason codes. It does not embed the complete evaluations; those remain separate deterministic output. The caller supplies `decision_id` and `decided_at`, so equal evaluations, policy, and metadata yield an equal decision without clock reads or random IDs. Policy consumes `RuleEvaluation` results only, never raw `RiskSignal`s.

## Current boundary

Composition is synchronous, deterministic, and infrastructure-independent. There is no persistence, HTTP decision endpoint, Kafka integration, ML, or LLM.
