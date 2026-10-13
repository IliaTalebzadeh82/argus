# Phase 01 / Checkpoint 03 — Policy composition and final decision

## Status
`PASS`

## Objective
Compose completed, versioned rule-set evaluations into one deterministic, explainable final `Decision`.

## Implemented
- Added a non-empty, immutable `RuleSetEvaluation` with rule-set identity/version, transaction subject ID, ordered evaluations, and duplicate-identity rejection.
- Added `DecisionPolicy` and a conservative Phase-1 policy with explicit BLOCK, uncertainty, REVIEW, CHALLENGE, and ALLOW precedence.
- Added stable reason de-duplication, policy reasons for clean ALLOW and non-BLOCK uncertainty, and caller-supplied decision ID/time.
- Added policy and rule-set identity/version to `Decision`; documented the three independent versioning roles and added 41 focused policy tests.

## Key decisions
- Rule version identifies implementation semantics; rule-set version identifies deployed configuration and membership; policy version identifies composition behavior. Publication/version discipline suffices without a registry.
- A matched BLOCK remains BLOCK even with uncertainty. Otherwise uncertainty yields REVIEW. All matched reasons remain in evaluation order; uncertainty reason is omitted when BLOCK already determines the action.
- Full evaluations stay separate from the final decision. The decision records actual Phase-1 producers only; no placeholder model metadata.

## Files changed
- Production: `src/argus/domain/models.py`, `src/argus/fraud/__init__.py`, `src/argus/fraud/rules.py`, `src/argus/fraud/policy.py`.
- Tests: `tests/unit/test_core_fraud_domain.py`, `tests/unit/test_fraud_rules.py`, `tests/unit/test_fraud_policy.py`.
- Architecture: `docs/architecture/core-fraud-domain.md`, `docs/architecture/rule-engine.md`, `docs/architecture/policy-engine.md`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 24 packages resolved, 23 checked.
- `uv run --locked pytest tests/unit/test_fraud_policy.py tests/unit/test_fraud_rules.py tests/unit/test_core_fraud_domain.py -q`: 119 passed, including 41 new focused policy tests.
- `make check`: Ruff lint and format passed; 137 tests passed, one existing Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed.
- `git diff --check` and `git diff --cached --check`: passed.
- First `make check` runs found import order, line length, and formatting in the new test file. Fixed them and reran; all checks passed.
- Runtime dependency changes: none. Compose changes: none. `Decision` schema changed by adding required `policy_id`, positive `policy_version`, `rule_set_id`, and positive `rule_set_version`; no model fields were added.

## Acceptance criteria
- [x] Rule, rule-set, and policy versions have distinct documented meanings; configuration changes can bump only the rule set.
- [x] Non-empty, immutable rule-set output carries subject identity and ordered, unique rule evaluations.
- [x] Policy consumes evaluations only and receives decision ID/time explicitly.
- [x] All specified precedence and uncertainty cases pass, including synthetic BLOCK and ALLOW recommendations.
- [x] Matched and policy-level reasons are machine-readable, stably ordered, and de-duplicated.
- [x] `Decision` stores actual rule-set and policy provenance and remains immutable.
- [x] No persistence, decision endpoint, Kafka, ML, LLM, new dependency, or Compose change.
- [x] Focused/full checks and Compose validation pass.
- [x] Implementation committed; report commit, push, remote HEAD, and clean worktree verification follow this report's creation.

## Architecture / invariants check
Master reference preserved. The critical path remains deterministic and independent of generative AI. PostgreSQL's future authority is unchanged. No ADR or deliberate deviation.

## Git
- Branch: `main`.
- Implementation commit: `20a25d5a0cb9c058715ee9f33fe2f2c78809539a`.
- Report commit: this report's commit; see final handoff for SHA.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verify after commit.
- Final `git status`: pending post-push verification.

## Resource / usage notes
No containers were started. Validation used the existing local environment; no builds or new packages.

## Risks / technical debt
Version publication and historical retrieval are manual until a later checkpoint defines storage and loading. The upstream Starlette/AnyIO warning remains.

## Next recommended checkpoint
Scope the next Phase-1 checkpoint separately, with explicit acceptance criteria for the next boundary. Preserve the pure rule/policy implementation when introducing persistence or transport later.

## Handoff notes for ChatGPT
Review `docs/architecture/policy-engine.md`, the policy matrix, and version-change test. The saved report cannot attest to its own push; use the final handoff for the report SHA, remote HEAD, and clean worktree confirmation.
