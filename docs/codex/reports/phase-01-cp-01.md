# Phase 01 / Checkpoint 01 — Core fraud domain language and invariants

## Status
`PASS`

## Objective
Define the deterministic, infrastructure-independent facts and historical decision result needed for future fraud evaluation.

## Implemented
- Added immutable Pydantic snapshots for users, devices, money, transactions, payment attempts, risk signals, and decisions.
- Added the four allowed actions, machine-readable reason codes, UTC timestamps, strict opaque IDs, typed scalar signals, and an immutable context that checks supplied references.
- Documented relationships and domain boundaries; added 37 focused domain tests.

## Key decisions
- Transactions and payment attempts have separate identities; devices have no single-user owner.
- Minor-unit integers represent money. Risk signals admit only boolean, integer, finite float, and string scalar values.
- Decision reasons are required, machine-readable codes. Rule, policy, model, and feature metadata wait for real producers and semantics. The context carries facts but does not evaluate them.

## Files changed
- Production: `src/argus/domain/__init__.py`, `src/argus/domain/models.py`.
- Architecture: `docs/architecture/core-fraud-domain.md`.
- Tests: `tests/unit/test_core_fraud_domain.py`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 24 packages resolved, 23 checked.
- `uv run --locked pytest tests/unit/test_core_fraud_domain.py`: 37 passed.
- `make check`: Ruff lint/format passed; 55 tests passed, one existing Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed.
- `git diff --check` and `git diff --cached --check`: passed.
- First focused run passed 34 tests. Added non-finite float and numeric-time rejection tests, formatted, and reran affected and full checks; all passed.
- Direct runtime dependency changes: none. Compose changes: none.

## Acceptance criteria
- [x] User, device, transaction, payment attempt, risk signal, decision, and four exact actions modeled.
- [x] Minor-unit money, currency normalization, strict IDs, aware UTC timestamps, typed signal provenance, reason codes, and immutability validated.
- [x] Many payment attempts per transaction and many-to-many user/device observations supported; context rejects mismatched references.
- [x] Architecture document and focused invariant tests added.
- [x] No rules, policy engine, persistence, transport, API behavior, ML, or LLM additions.
- [x] Full check and Compose validation pass.
- [x] Implementation committed; report commit, push, remote HEAD, and clean worktree verification follow this report's creation.

## Architecture / invariants check
Master reference preserved. PostgreSQL remains designated authoritative, Redis derived, Kafka transport; no application coupling was added. Decision history is immutable and deterministic. No ADR or deliberate deviation.

## Git
- Branch: `main`.
- Implementation commit: `e2f213def43e3363d9a97263f0b979bbc1359ccf`.
- Report commit: this report's commit; see final handoff for SHA.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verify after commit.
- Final `git status`: pending post-push verification.

## Resource / usage notes
No containers were started. Validation used the existing local environment; no new dependencies or builds.

## Risks / technical debt
Decision reproducibility metadata and evidence-to-reason mapping require concrete rules and policy versions in later checkpoints. The upstream Starlette/AnyIO deprecation warning remains.

## Next recommended checkpoint
Scope a separate Phase 1 checkpoint for deterministic rule evaluation over these facts. Keep persistence and API decisioning in their designated checkpoints.

## Handoff notes for ChatGPT
Review the domain model and architecture document against the stated invariants. The saved report cannot attest to its own push; use the final handoff for the report SHA, remote HEAD, and clean worktree confirmation.
