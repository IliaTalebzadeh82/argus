# Phase 03 / Checkpoint 02 — Legitimate synthetic world

## Status
`PASS`

## Objective
Generate a deterministic legitimate population, payment snapshots, and production-compatible fraud events from the CP01 kernel.

## Implemented
- Added immutable, validated legitimate scenario configuration and canonical JSON behavior metadata.
- Generated users, unique devices, deterministic merchant IDs, transactions, payment attempts, and chronologically scheduled event records.
- Added deterministic UUIDv5 event IDs, stable traces, V1 production contract validation, architecture documentation, and focused tests.

## Key decisions
- Kept `SIMULATOR_VERSION = 1`; CP01 kernel semantics did not change.
- Per-user `amount`, `merchant`, and `outcome` random streams separate independent draws. Scoped transaction/payment allocator kinds preserve existing users' identities as population grows.
- UUIDv5 name uses canonical kernel manifest plus scenario config, event type, and logical subject ID. Config changes identify a different simulated world; population growth therefore changes event UUIDs, while earlier users' behavior stays local.
- Planned user/payment actions are sorted by event time and planning ordinal. The virtual clock only advances; baseline production time equals event time.

## Files changed
- Behavior: `src/argus/simulation/legitimate.py`.
- Tests: `tests/unit/test_legitimate_simulation.py`.
- Architecture: `docs/architecture/synthetic-legitimate-world.md`; small link in `docs/architecture/simulation-kernel.md`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 33 resolved, 31 checked.
- `uv run --locked pytest tests/unit/test_simulation_kernel.py tests/unit/test_legitimate_simulation.py -q`: **32 passed**.
- `make check`: Ruff lint/format passed; **208 offline tests passed**, one upstream Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed; no Compose changes or startup.
- `git diff --check` and `git diff --cached --check`: passed.
- Initial `make check` found line formatting and two lambda lint errors. Formatted the files, replaced lambdas, added timing/zero-payment coverage, and reran all required checks successfully.

## Acceptance criteria
- [x] Immutable validated behavior config; canonical metadata; simulator version 1; no new dependency.
- [x] One unique device per user; deterministic merchants, scoped entity IDs, UUIDv5 events, and traces.
- [x] Scheduled account/payment/terminal times and deterministic equal-time tie order; produced/generated times match occurred time.
- [x] Integer minor-unit amounts, separate random dimensions, normal payment failures, and exactly one terminal event per payment.
- [x] Every generated event passes V1 validation; no chargeback, promo, fraud, duplicate, lateness, infrastructure I/O, ML, or labels.
- [x] Same complete inputs reproduce full results; seed, time, and population locality verified.
- [x] Reference projector yields `accounts_on_device=1`, `payments_10m=3`, and `failed_payments_1h=3` in the controlled scenario.
- [x] Focused/full offline checks and Compose configuration passed; implementation committed. Report commit/push/remote checks follow this report.

## Architecture / invariants check
Master reference preserved. No ADR or deliberate deviation. PostgreSQL authority, at-least-once processing, and the critical decision path are untouched. The scenario is pure in-memory behavior.

## Git
- Branch: `main`.
- Implementation commit: `d07c1fe128b6f797a88d6c39cad3d6d387dc153b` (`phase-03/cp-02: add legitimate synthetic behavior`).
- Report commit: this report's commit; SHA supplied in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending report commit; final handoff verifies it.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Only offline tests and Compose configuration validation ran. No containers started. No token estimate is available.

## Risks / technical debt
Exact random output is scoped to the declared Python 3.13 and locked environment. The result is in memory; dataset export belongs to a later checkpoint.

## Next recommended checkpoint
Implement the separately scoped Phase 03 fraud/coordinated synthetic behaviors after review of this legitimate baseline.

## Handoff notes for ChatGPT
Scenario fields are `user_count`, `payments_per_user`, `merchant_count`, `payment_failure_probability`, `min_amount_minor`, `max_amount_minor`, `currency`, `account_spacing`, `first_payment_delay`, `payment_spacing`, and `terminal_delay`. The baseline emits only `account.created`, `payment.attempted`, `payment.failed`, and `transaction.completed`. Focused tests cover contract counts, event UUIDs, chronology, full repeat, seed/time separation, population and random-dimension locality, and Phase 2 projector semantics.
