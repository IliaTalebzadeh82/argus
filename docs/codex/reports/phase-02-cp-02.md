# Phase 02 / Checkpoint 02 — Redis derived feature projection

## Status
`PASS`

## Objective
Store CP01-equivalent derived online features in Redis with atomic event idempotency, atomic snapshots, and explicit projection lifecycle and loss behavior.

## Implemented
- Added a synchronous, explicitly constructed Redis client and versioned projection keys.
- Added Lua operations for lifecycle transitions, event application, and atomic snapshot queries. Canonical event identity is shared with the CP01 reference.
- Changed local Redis to `noeviction`; documented derived authority, failure, and retention semantics.
- Added seven real-Redis integration tests and an explicit integration command.

## Key decisions
- Integer microseconds since the Unix epoch are Redis sorted-set scores; timestamps beyond exact double-integer range are rejected.
- Identity uses a Redis hash; payment/failure event IDs and earliest device/user observations use sorted sets. Opaque IDs are UTF-8 hex encoded in keys.
- `UNINITIALIZED` and `REBUILDING` reject queries. `READY` allows queries and live application. No in-place ready-to-rebuilding transition or automatic initialization.
- Redis remains derived and unbounded; a write failure surfaces explicitly, and replay is required after state loss.

## Files changed
- Projection/client: `src/argus/features/redis_projection.py`, `src/argus/features/__init__.py`; shared identity: `src/argus/events/features.py`.
- Dependency/config/command: `pyproject.toml`, `uv.lock`, `compose.yaml`, `Makefile`.
- Tests: `tests/integration/test_redis_feature_projection.py`.
- Architecture: `docs/architecture/redis-feature-projection.md`, `docs/architecture/local-infrastructure.md`, `docs/architecture/feature-pipeline-semantics.md`.

## Validation
- `uv lock && uv sync --locked`: passed; resolved `redis==8.1.0`.
- `ARGUS_REDIS_URL=redis://localhost:6379/0 make test-redis-integration`: **7 passed** against Redis `7.2.16`, `noeviction`, `maxmemory=402653184`, snapshots/AOF disabled.
- Concurrent duplicate test: one `APPLIED`, one `DUPLICATE`, one feature contribution.
- Redis restart/loss/rebuild campaign: snapshot `(1, 1, 1)` matched CP01 before restart; restart returned `UNINITIALIZED` rather than zeros; deterministic replay restored reference equality.
- `make check`: Ruff lint/format passed; **161 offline tests passed**, one existing Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`, `git diff --check`, and `git diff --cached --check`: passed.
- `make test-redis-integration` without `ARGUS_REDIS_URL`: expected failure, confirming no implicit developer Redis connection.
- Initial Ruff run found long lines; formatted code and shortened one docstring, then reran successfully. Local Compose stack stopped with `docker compose down`; `docker compose ps` empty.

## Acceptance criteria
- [x] Explicit Redis client, compatible dependency, versioned collision-free keys, and `noeviction`.
- [x] Lifecycle rejects uninitialized/rebuilding queries and invalid transitions; Redis loss requires replay.
- [x] Canonical identity, exact duplicate/conflict handling, atomic apply, and concurrent duplicate safety.
- [x] CP01-equivalent microsecond windows, historical device observations, out-of-order replay, and no-feature event identity.
- [x] Atomic caller-time snapshot queries, explicit operational failures, real Redis tests, and restart/rebuild exercise.
- [x] Offline checks remain Redis-independent; no Decision/Investigator API, worker, Kafka, PostgreSQL, ML, or LLM changes.
- [x] Architecture docs and implementation/report commits completed; push and remote verification follow this report commit.

## Architecture / invariants check
Master reference preserved: PostgreSQL is authoritative for decisions, Redis is derived. No ADR or deliberate deviation. No TTL, watermark, or retention policy was added.

## Git
- Branch: `main`.
- Implementation commit: `df877beb361f4d5d8beb6e46b65956c973c94951`.
- Report commit: this report's commit; SHA in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verified in final handoff.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Only Redis was started for integration work; the full offline suite ran once after focused tests. No measured token or performance metric is available.

## Risks / technical debt
State is intentionally unbounded. Redis Lua scripts serialize operations but do not roll back earlier commands on runtime error; a failed write must be treated as an unknown outcome and reconciled or redelivered by a future worker. No worker recovery policy exists yet.

## Next recommended checkpoint
Scope the event transport and feature worker separately, including replay, offset handling, and recovery from Redis write failures. Do not infer retention or lateness policy from CP02.

## Handoff notes for ChatGPT
Review the Lua apply/query boundaries and the documented Redis loss semantics. The report cannot attest to its own push; the final response carries report SHA, remote HEAD, and clean-worktree confirmation.
