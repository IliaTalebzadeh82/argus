# Phase 02 / Checkpoint 05 — Lag, freshness, rebalance, and failure campaign

## Status
`PASS`

## Objective
Measure Kafka transport lag, stale READY decisions, late event-time arrivals, consumer rebalances, and poison blockage without changing decision or worker production semantics.

## Implemented
- Added an operator-only Kafka Admin lag probe with immutable per-partition and total results, explicit no-commit state, offset validation, JSON CLI, and `make feature-lag`.
- Added six offline lag-math tests and four real Kafka/Redis/PostgreSQL campaign tests for lag, stale decisions/replay, late events, two-worker rebalance, duplicate/out-of-order convergence, and poison blockage.
- Documented observed results in `docs/experiments/phase-02-lag-freshness.md` and the conceptual boundary in `docs/architecture/feature-freshness.md`.

## Key decisions
- Missing group commit is `null`; for this group's `earliest` policy, pending retained records are `high-low`. A valid commit yields `high-committed`; invalid/out-of-range positions fail. The Admin probe does not join the group or feed API readiness.
- READY, zero transport lag, and event-time completeness remain separate. The experiment showed READY/200 readiness and 30 pending events could still yield a historically durable ALLOW, while a later new-key decision yielded CHALLENGE.
- No Kafka lag gate, watermark, request-time payment adjustment, poison recovery/DLQ, schema migration, or model signal was introduced. Future consistency policy needs a defined guarantee and separate design.

## Files changed
- Probe/commands: `src/argus/events/kafka_lag.py`, `Makefile`, `README.md`.
- Tests: `tests/unit/test_kafka_lag.py`, `tests/integration/test_phase02_failure_semantics.py`.
- Evidence/architecture: `docs/experiments/phase-02-lag-freshness.md`, `docs/architecture/feature-freshness.md`; this report.

## Validation
- `uv sync --locked`: passed; 33 packages resolved, 31 checked.
- `make check`: Ruff lint/format passed; **176 offline tests passed**, one existing Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed. Host `ARGUS_DATABASE_URL=... uv run --locked alembic upgrade head`: passed against local PostgreSQL, no new migration.
- `ARGUS_KAFKA_BOOTSTRAP_SERVERS=localhost:9092 make feature-lag`: passed; final live-topic partitions had low/high/committed `0/43/43`, `0/31/31`, `0/44/44`, total pending **0**. The initial probe showed a partition with no commit as `null`.
- `ARGUS_KAFKA_BOOTSTRAP_SERVERS=localhost:9092 ARGUS_REDIS_URL=redis://localhost:6379/0 ARGUS_DATABASE_URL=postgresql+psycopg://argus:argus_dev_only@localhost:5432/argus make test-phase02-failures`: **4 passed** in 34.63 seconds against Kafka 4.3.1, Redis 7.2.16, PostgreSQL 17.11. Default live topic/group stale campaign: baseline lag 0, induced backlog 30, Redis/reference payments 0/30, readiness 200, ALLOW; 30 drained to zero in **4.515 seconds** in a focused measured run, new-key CHALLENGE, original-key replay ALLOW. Zero-lag late arrival: payments 0→5 and ALLOW→CHALLENGE. Two-member assignments [0,1]/[2] became one-member [0,1,2]; 16 deliveries for 12 logical events, 5 duplicate results including rebalance redelivery, final Redis/reference equality. Poison offset 1 redelivered after restart, commit stayed at 1, two records pending including valid B.
- `git diff --check`, `git diff --cached --check`: passed. `rg` confirmed Decision API has no Kafka import/query. `docker compose down`; `docker compose ps` empty.
- During iteration, a wrong Confluent import and a test Admin-client lifetime issue failed and were fixed. A rebalance test initially discarded a polled record and assumed all records were drained only after stabilization; it now processes during rebalance and both workers commit before one leaves. Final focused and offline passes succeeded.

## Acceptance criteria
- [x] Admin-only per-partition low/high/committed diagnostic, correct pending math, explicit no-commit, invalid-offset failure, CLI and offline tests.
- [x] Real lag grew with stopped consumption and fell to zero after committed catch-up; Redis stayed READY and API readiness 200 during backlog.
- [x] Redis/reference divergence, stale ALLOW, post-catch-up CHALLENGE, and PostgreSQL historical ALLOW replay demonstrated.
- [x] Late-event arrival changed historical features and a new decision despite zero lag before and after; current-payment request/event race analyzed.
- [x] Two workers shared three partitions and one acquired all on rebalance; Redis/reference converged with duplicates and out-of-order events.
- [x] Poison repeated at the same offset after restart and blocked the following valid record; no recovery policy added.
- [x] Architecture and experiment reports complete; no API Kafka dependency, readiness gate, watermark, schema migration, ML/LLM, or production behavior change.
- [x] Offline and focused real-infrastructure checks passed; stack stopped, commits and remote verification completed at final handoff.

## Architecture / invariants check
Master reference preserved: PostgreSQL remains authoritative for decisions/audit, Redis is derived, Kafka delivery is at least once, and the critical path remains deterministic. No ADR or deliberate architectural deviation. Production behavior and database schema unchanged.

## Git
- Branch: `main`.
- Implementation commit: `2c3ba247d3b0153994b269267f531662b0dc7e03`.
- Report commit: this report's commit; SHA in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verified in final handoff.
- Final `git status`: pending post-push verification.

## Resource / usage notes
One local Compose stack was used and stopped. The focused default-topic run measured 30 records drained in 4.515 seconds with synchronous per-message commits. This local timing is not a benchmark or production SLO. Full offline checks ran after final code edits; no token estimate is available.

## Risks / technical debt
READY permits lagging-but-valid decisions. Zero broker lag cannot prove future late events are absent. Poison records indefinitely block a partition under the present fail-stop worker. The existing unbounded Kafka/Redis history and per-message commit cost remain deliberate Phase-2 debt.

## Next recommended checkpoint
Have the phase review evaluate whether freshness needs an observability SLO, request-specific processing barrier, or another explicit contract. Define the desired guarantee and availability trade-off before changing readiness. Do not treat zero lag as an event-time watermark.

## Handoff notes for ChatGPT
Review the exact evidence in `docs/experiments/phase-02-lag-freshness.md` and offset conventions in `docs/architecture/feature-freshness.md`. The API intentionally has no Kafka dependency. The report cannot attest to its own push; final response supplies report SHA, remote HEAD, and clean-worktree confirmation.
