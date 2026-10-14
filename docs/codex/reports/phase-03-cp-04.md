# Phase 03 / Checkpoint 04 — Mixed workload, lateness, and duplicate delivery

## Status
`PASS`

## Objective
Compose legitimate and coordinated-fraud facts into one deterministic, pure workload with distinct canonical events, production times, and delivery attempts.

## Implemented
- Added immutable mixed-world and traffic configurations, a combined result, canonical events, delivery records, and UTC minute traffic summary.
- Added optional opaque identity scopes to separate scenario kernels while preserving standalone default behavior.
- Added event-local production delays and exact duplicate delivery attempts; stable delivery-time order uses one-based simulator sequence.
- Added 18 focused workload tests and architecture documentation.

## Key decisions
- Scope = first twelve hex digits of SHA-256 over the versioned internal scenario namespace; production IDs contain only opaque scope, not cohort words. Scoped scenario IDs are stable as the other cohort grows.
- Traffic streams use scoped subject ID plus event type, separately for late selection, delay, and duplicate selection. This remains local even when a scenario config change remints CP02/CP03 UUIDs.
- Canonical `event_id` remains logical identity; production delay changes only `produced_at`. Exact duplicate records share the same envelope object. Distinct delay variants are alternate experimental histories because the Phase-2 identity includes `produced_at`.
- Simulator version remains **1**; existing kernel default and standalone scenario semantics are unchanged.

## Files changed
- Simulation: `src/argus/simulation/{ids,kernel,workload}.py`.
- Tests: `tests/unit/test_synthetic_workload.py`.
- Architecture: `docs/architecture/synthetic-workload.md`, small note in `docs/architecture/simulation-kernel.md`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 33 resolved, 31 checked.
- `uv run --locked pytest tests/unit/test_simulation_kernel.py tests/unit/test_legitimate_simulation.py tests/unit/test_fraud_simulation.py tests/unit/test_synthetic_workload.py -q`: **84 passed**.
- `make check`: Ruff lint and format passed; **260 offline tests passed**, one pre-existing Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed; no startup.
- `git diff --check` and `git diff --cached --check`: passed after removing one documentation EOF blank line.
- Initial lint found import ordering, a long test comment, and missing `zip(strict=...)`; fixed all before final checks.
- Controlled sample: seed 17, 3 legitimate users, 4 fraud users, 3 legitimate devices, 1 fraud shared device, 21 transactions and attempts. With late probability 1, delay 0–12 minutes, duplicate probability 0.5 and delay 2 seconds: **49 canonical events, 76 deliveries, 27 duplicates, 49 late events**. The UTC 00:10 minute bucket has 9 deliveries; ordered buckets sum to 76.
- Inversion example: event `d5bb7b57-8131-52fa-a654-bc561be97f2f` occurred 00:00:05 and delivered 00:00:36.582140 UTC at sequence 1; event `83f8e0c2-5d85-537d-8e2b-873a1a07e3fc` occurred earlier at 00:00:03 and delivered later at 00:00:43.421554 UTC at sequence 2.
- Reference projector: **49 APPLIED, 27 DUPLICATE**, no identity conflict; final snapshots match unique canonical history. Legitimate device count is 1, fraud shared-device count is 4, and controlled fraud user has 3 recent attempts and 3 recent failures.
- No dependency or Compose changes.

## Acceptance criteria
- [x] CP01–CP03 behavior and tests preserved; mixed IDs collision-free, opaque, and referentially coherent.
- [x] World truth stays simulator-only; one canonical event per fact, distinct from exact duplicate deliveries.
- [x] Traffic configuration does not change world facts or logical IDs; event-local randomness and separate fault dimensions verified.
- [x] Produced time never precedes occurrence; delivery order is chronological with stable equal-time ties and a proven event-time inversion.
- [x] Projector APPLIED/DUPLICATE accounting and feature equivalence across lateness and duplicate variants verified.
- [x] Pure summary, architecture note, offline checks, Compose validation, implementation commit completed.
- [x] Report commit, push, remote HEAD, and clean worktree verified in final handoff after report creation.

## Architecture / invariants check
Master reference preserved. No ADR or deliberate deviation. PostgreSQL authority, Phase-2 event identity, feature-time semantics, and critical decision path are unchanged. No Kafka, Redis, HTTP, database, filesystem export, ML, watermark, or real-time execution entered this workload.

## Git
- Branch: `main`.
- Implementation commit: `8275edb9ac70b6bc5d9e6a98483cbdfe047c936f` (`phase-03/cp-04: compose synthetic traffic workload`).
- Report commit: this report's commit; SHA supplied in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending report commit; final handoff verifies it.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Only offline tests and Compose configuration validation ran. No containers started. No token estimate is available.

## Risks / technical debt
The opaque scope is twelve hex digits of a fixed digest and is designed for these two known scenario namespaces. PRNG reproduction remains scoped to Python 3.13 and the locked environment. The schedule is in memory and has no execution adapter in CP04.

## Next recommended checkpoint
Phase 03 / Checkpoint 05 may consume the pure schedule through separately scoped publication or export adapters. No such adapter was implemented here.

## Handoff notes for ChatGPT
`MixedWorkloadResult` retains both child results, both configs, canonical metadata, combined production facts, canonical envelopes, scheduled delivery attempts, and summary. A duplicate repeats the exact envelope, while delay variants must be treated as alternate projector histories. The test suite proves scope locality across appended users/rings despite scenario UUID reminting.
