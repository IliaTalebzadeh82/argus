# Phase 03 / Checkpoint 05 — Workload export and Kafka playback

## Status
`PASS`

## Objective
Export a reproducible CP04 mixed workload bundle and publish its scheduled deliveries through the existing Kafka producer, then prove Redis converges to the pure reference projection.

## Implemented
- Added immutable typed `WorkloadSpec`, canonical JSON parsing/serialization, and a checked-in demo spec.
- Added staged deterministic JSON/JSONL bundle export, SHA-256 checksums, and file/count/reference verification with separated production, event, transport, and truth data.
- Added sequential unpaced and monotonic paced playback, an immutable report, and export/publish CLI commands.
- Added offline adapter tests, isolated real Kafka/Redis integration test, architecture documentation, and concise README/Make commands.

## Key decisions
- Bundle format **1**, simulator version **1**, and production event version **1** are separate version domains. Exported canonical events reuse the exact production Kafka wire serializer.
- The destination must not exist. Export verifies a temporary sibling before same-filesystem rename; repeated exports cannot mix histories.
- Each delivery makes one acknowledged publish call, including deliberate duplicate attempts. Producer idempotence does not remove application-level duplicates. Kafka preserves ordering per partition, not the simulator's global schedule.
- Playback stops on failure without resume state. Rerunning into the same namespace may add deliveries.

## Files changed
- Spec/example: `src/argus/simulation/spec.py`, `configs/simulation/phase-03-demo.json`.
- Adapters/CLI: `src/argus/simulation/{export,playback,cli}.py`.
- Tests: `tests/unit/test_simulation_adapters.py`, `tests/integration/test_simulation_kafka_playback.py`.
- Documentation/commands: `docs/architecture/simulation-adapters.md`, `README.md`, `Makefile`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 33 packages resolved, 31 checked.
- `uv run --locked pytest tests/unit/test_simulation_kernel.py tests/unit/test_legitimate_simulation.py tests/unit/test_fraud_simulation.py tests/unit/test_synthetic_workload.py tests/unit/test_simulation_adapters.py -q`: **89 passed**.
- `make check`: Ruff lint/format passed; **265 offline tests passed**, one existing Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed; no Compose changes.
- Demo export twice to distinct temporary paths, `diff -rq`, `sha256sum -c checksums.sha256`, `verify_bundle`: identical file bytes; all **10** payload checksums passed; **58** canonical events and **84** deliveries verified. Exported files: `metadata.json`; `production/{users,devices,transactions,payment-attempts}.jsonl`; `events/canonical-events.jsonl`; `transport/delivery-schedule.jsonl`; `truth/{fraud-rings,card-uses,promo-redemptions}.jsonl`; `checksums.sha256`.
- Demo counts: **8 users, 5 devices, 24 transactions, 24 payment attempts; 1 ring, 12 card uses, 4 promo redemptions; 58 logical events, 84 deliveries, 26 duplicates, 28 late logical events**.
- `ARGUS_KAFKA_BOOTSTRAP_SERVERS=localhost:9092 ARGUS_REDIS_URL=redis://localhost:6379/0 make test-simulation-kafka`: **1 passed** (unpaced). An isolated `argus.cp05.test.<uuid>` topic had **3 partitions**, **84** broker records, user-ID keys, and complete duplicate envelopes. Rebuild from `UNINITIALIZED` reached `READY`: **58 APPLIED**, **26 DUPLICATE**; final Redis snapshots for all 8 users equaled the pure canonical reference. No cross-partition global order was assumed.
- `docker compose stop kafka redis`: passed; final stack has no running services. `git diff --check` and `git diff --cached --check`: passed.
- During validation, a new verifier check compared ISO timestamps lexically and rejected valid variable-width fractional seconds. Changed it to parse timestamps as datetimes; focused tests and full offline checks passed. Ruff import order was fixed.
- No dependencies or Compose changes. Synchronous producer timing was not treated as a capacity measure.

## Acceptance criteria
- [x] Pure generators unchanged; typed spec round-trips and reconstructs an identical workload.
- [x] Canonical, deterministic, checksum-verified bundle with production/truth separation and referential integrity.
- [x] Exported events round-trip through the production wire contract; delivery references and attempt counts verify.
- [x] Destination safety, CLI export/publish, monotonic paced and unpaced playback, stop-on-failure behavior.
- [x] Real Kafka count, keys, duplicate publication, Redis rebuild, and canonical reference equality.
- [x] CP01–CP04 tests and full offline checks pass; no ML dataset, watermark, Decision API load, or producer optimization.
- [x] Implementation committed; report commit, push, remote HEAD, and clean worktree verified in final handoff after report creation.

## Architecture / invariants check
Master reference preserved. No ADR or deliberate deviation. PostgreSQL authority and critical decision path are untouched; Redis remains derived. Truth remains simulator-only, and at-least-once delivery is explicit.

## Git
- Branch: `main`.
- Implementation commit: `f107ddb89b47c087cd6d651fba8923314ed4f9ca` (`phase-03/cp-05: add workload export and Kafka playback`).
- Report commit: this report's commit; SHA supplied in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending report commit; final handoff verifies it.
- Final `git status`: pending post-push verification.

## Resource / usage notes
One 84-record local Kafka/Redis integration campaign ran, plus a rerun after stronger assertions. Kafka and Redis were stopped. No token count estimate is available.

## Risks / technical debt
Playback has no resume/checkpoint state, and rerunning in an existing namespace adds duplicates. Exact PRNG output remains scoped to Python 3.13 and the locked environment. Bundle verification checks current format integrity, not arbitrary untrusted schema evolution.

## Next recommended checkpoint
Review Phase 03 against its gate and prepare a separately scoped phase closure decision. Do not begin Phase 4 dataset construction as part of this checkpoint.

## Handoff notes for ChatGPT
The demo spec is canonical JSON with seed 17. Offline exports match byte for byte across paths. The real test provisions a unique topic and Redis namespace, checks exact broker high-watermark count, records APPLIED/DUPLICATE outcomes during rebuild, and compares all generated users' feature snapshots to the pure reference.
