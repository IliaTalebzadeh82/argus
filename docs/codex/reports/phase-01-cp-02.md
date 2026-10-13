# Phase 01 / Checkpoint 02 — Deterministic rule evaluation

## Status
`PASS`

## Objective
Evaluate three fraud conditions deterministically from supplied domain facts, while preserving evidence and deferring final decisions to policy composition.

## Implemented
- Added an explicit rule protocol, three immutable configured integer-count rules, and a rule engine that returns every evaluation in registration order.
- Added three-state results, machine-readable diagnostics, strict result invariants, and exact signal evidence attribution.
- Documented the rule/policy boundary and added 41 focused rule tests.

## Key decisions
- Rules select signals by code plus logical source; missing, duplicate, and wrongly typed evidence produce `INDETERMINATE`.
- A valid non-match retains the examined signal, while a match carries a recommendation, reason code, and evidence. The engine does not resolve conflicting recommendations.
- Thresholds and sources are explicit, positive rule versions identify behavior, and duplicate `(rule_id, rule_version)` registrations fail.

## Files changed
- Production: `src/argus/fraud/__init__.py`, `src/argus/fraud/rules.py`.
- Architecture: `docs/architecture/rule-engine.md`.
- Tests: `tests/unit/test_fraud_rules.py`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 24 packages resolved, 23 checked.
- `uv run --locked pytest tests/unit/test_fraud_rules.py`: 41 passed.
- `make check`: Ruff lint/format passed; 96 tests passed, one existing Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed.
- `git diff --check` and `git diff --cached --check`: passed.
- Initial focused run: 38 passed. Added machine-readable result validation and three invariant cases; focused run then passed 41 tests.
- Runtime dependency changes: none. Compose changes: none.

## Acceptance criteria
- [x] Rule protocol, stable ID, positive version, and exactly three evaluation states.
- [x] Matched recommendation/reason/evidence and indeterminate diagnostic; coherent result invariants enforced.
- [x] Missing, wrong-source, ambiguous, and invalid-type signals handled without treating them as safe evidence.
- [x] Three threshold-configured deterministic rules with no I/O, clock, or generated IDs.
- [x] Engine evaluates all rules in order, preserves conflicts, rejects duplicate identities, and repeats equal results.
- [x] Rule/policy boundary documented; no final `Decision`, policy, persistence, API, Kafka, feature computation, ML, or LLM work.
- [x] Focused and full tests pass; Compose validates; no new dependencies.
- [x] Implementation committed; report commit, push, remote HEAD, and clean worktree verification follow this report's creation.

## Architecture / invariants check
Master reference preserved. Rules remain pure and synchronous; generative AI has no critical-path role. No ADR or deliberate deviation.

## Git
- Branch: `main`.
- Implementation commit: `76bf806f057f1c9043e590b4f16bc773a32cfb2e`.
- Report commit: this report's commit; see final handoff for SHA.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verify after commit.
- Final `git status`: pending post-push verification.

## Resource / usage notes
No containers started. Validation used the existing local environment; no new dependencies or builds.

## Risks / technical debt
Rule version changes are a developer responsibility until later reproducibility and policy work defines publication and historical loading semantics. The upstream Starlette/AnyIO warning remains.

## Next recommended checkpoint
Phase 01 / Checkpoint 03 should define policy composition from these independent rule evaluations into a final action and `Decision`; it should explicitly settle conflict and indeterminate handling.

## Handoff notes for ChatGPT
Review the three-state semantics, evidence selection, and the absence of policy decisions. The saved report cannot attest to its own push; use the final handoff for the report SHA, remote HEAD, and clean worktree confirmation.
