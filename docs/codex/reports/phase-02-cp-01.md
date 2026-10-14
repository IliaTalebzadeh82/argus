# Phase 02 / Checkpoint 01 — Event vocabulary and pure feature semantics

## Status
`PASS`

## Objective
Define the five typed Phase 2 fraud facts and an exact, pure event-time reference for the three existing rule inputs.

## Implemented
- Added frozen, closed payloads for `account.created`, `payment.attempted`, `payment.failed`, `transaction.completed`, and `chargeback.received`, all version 1.
- Added an explicit type/version/payload/subject validator and an in-memory projector with `APPLIED`, `DUPLICATE`, and event-ID conflict behavior.
- Added immutable UTC feature snapshots, contract/semantics documentation, and 15 focused tests.

## Key decisions
- Envelope `event_id` is producer-supplied logical identity. Exact recorded-event equality is a duplicate; reusing an ID for different payload or metadata is a conflict. `produced_at` participates in identity comparison but never in feature windows.
- Windows use `occurred_at`: `(as_of - 10 minutes, as_of]` and `(as_of - 1 hour, as_of]`. Device accounts are distinct users observed at or before `as_of`; unknown device is `None`, while a known device with no matching facts is zero.
- The reference retains full history to preserve arbitrary out-of-order and replay correctness. No retention or lateness policy is implied.

## Files changed
- Event contracts: `src/argus/events/fraud.py`; `docs/architecture/event-contract.md`.
- Feature reference: `src/argus/events/features.py`; `docs/architecture/feature-pipeline-semantics.md`.
- Tests: `tests/unit/test_fraud_features.py`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 31 packages resolved, 29 checked.
- `uv run --locked pytest tests/unit/test_fraud_features.py`: **15 passed**.
- `make check`: Ruff lint and format passed; **161 offline tests passed**, one existing Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed.
- `git diff --check` and `git diff --cached --check`: passed.
- Initial `make check` found one unused test import; removed it and reran successfully. No application failure.

## Acceptance criteria
- [x] Five version-one payloads use the existing typed envelope; producer supplies event ID/time/trace.
- [x] Fraud validation rejects type/version/payload/subject mismatch, bad IDs, extras, and naive timestamps.
- [x] Three exact feature definitions, time boundaries, future-event exclusion, UTC snapshots, and no-device semantics are implemented and tested.
- [x] Duplicate payment, failure, and account facts change state once; same-ID semantic and metadata conflicts fail explicitly.
- [x] Out-of-order delivery, replay with duplicates, produced-time independence, and repeated queries preserve feature truth.
- [x] Pure reference has no I/O or clock reads; Decision API, database schema, Compose services, dependencies, and infrastructure integration remain unchanged.
- [x] Documentation and required validation are complete; push and remote verification follow report commit.

## Architecture / invariants check
Master reference preserved. PostgreSQL remains authoritative for transactional/audit state; this in-memory projection is a correctness reference. No ADR or deliberate architectural deviation. No Kafka partition decision, Redis behavior, ML, or LLM work was introduced.

## Git
- Branch: `main`.
- Implementation commit: `3fd46189ebd4c268cce2790850b120dc488968b4`.
- Report commit: this report's commit; SHA in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verified in final handoff.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Only focused tests and one full offline check were run; no Docker startup. No measured token or performance metric is available.

## Risks / technical debt
The reference retains all logical events; later bounded distributed state needs a separately chosen retention/lateness policy. The existing Starlette/AnyIO deprecation warning remains.

## Next recommended checkpoint
Scope the first distributed feature-pipeline integration separately, using this projector as the correctness oracle. Do not infer Kafka or Redis policy from this reference implementation.

## Handoff notes for ChatGPT
Review `docs/architecture/feature-pipeline-semantics.md` and the 15 new tests for exact window and identity semantics. The report cannot attest to its own push; the final response carries the report SHA, remote HEAD, and clean-worktree confirmation.
