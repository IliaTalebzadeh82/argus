# Phase 01 / Checkpoint 05 — Decision API, idempotency, and PostgreSQL runtime semantics

## Status
`PASS`

## Objective
Expose a synchronous deterministic payment decision API with PostgreSQL audit persistence, request idempotency, and explicit dependency health/failure behavior.

## Implemented
- Added `POST /v1/decisions/payment` over validated `DecisionContext`, a versioned three-rule deployment, policy composition, and atomic audit persistence.
- Added canonical normalized-request SHA-256 fingerprints and PostgreSQL idempotency claims; replay returns the stored decision, key reuse returns 409, and failed transactions release the key.
- Added migration `64d97b805b13` after `09fc42332bec`, readiness checks, lifecycle-owned engine with `pool_pre_ping`, API error codes, and Compose PostgreSQL dependency.
- Documented the request path and added pure, real PostgreSQL API, and concurrent claim tests.

## Key decisions
- A unique key claim and deferred foreign key to the decision row make one transaction the concurrency and completeness boundary. No process mutex or request write retry is used.
- Rule membership, source `caller`, and demonstration thresholds 5/3/3 are static under rule set `phase1_payment` version 1; changes require a version bump. Policy `conservative_fraud` version 1 remains the sole composer.
- UUID and UTC time are injectable application-boundary providers. HTTP success is returned only after `engine.begin()` commits.
- Database connection failure is HTTP 503, immutable fact conflict and key reuse are HTTP 409; rule uncertainty can yield a persisted business REVIEW.

## Files changed
- Application/persistence: `src/argus/apps/decision_api/`, `src/argus/persistence/database.py`, `src/argus/persistence/schema.py`, `migrations/versions/64d97b805b13_decision_idempotency.py`.
- Tests: `tests/unit/test_decision_api.py`, `tests/integration/test_decision_api.py`, `tests/test_app_health.py`.
- Runtime/docs: `compose.yaml`, `README.md`, `docs/architecture/decision-api.md`, `application-boundaries.md`, `postgres-persistence.md`, `local-infrastructure.md`.

## Validation
- `uv sync --locked`: passed; no direct dependency changes.
- `make check`: Ruff lint/format passed; 146 pure/API tests passed, one existing Starlette/AnyIO deprecation warning.
- `ARGUS_DATABASE_URL=... make test-integration`: 7 real PostgreSQL tests passed, including 3 new API tests covering persistence, replay, key conflict, rollback/key reuse, policy paths, validation, fixed ID/clock, and concurrent same-key claims.
- `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`, `alembic current`, `alembic check`: passed; current `64d97b805b13 (head)`, no schema drift.
- `docker compose config --quiet`: passed. `docker compose up -d --build --wait --wait-timeout 180`: passed; both APIs healthy.
- Real container HTTP: Decision live 200, ready 200, Investigator live 200. First POST 200 with `replayed=false`; identical retry 200 with same decision and `replayed=true`; changed request on same key 409.
- Stopped PostgreSQL: Decision live 200, ready 503, POST 503 with `DATABASE_UNAVAILABLE`. Restarted PostgreSQL without Decision API restart: ready 200 and POST 200. Rebuilt final Decision API source and confirmed ready 200.
- Final `make check`, integration suite, `docker compose config --quiet`, and `git diff --check`: passed. `make infra-down`: passed; named volumes retained and stack stopped.
- An initial final `make check` found one unformatted test file; formatted it and reran all affected checks successfully.

## Acceptance criteria
- [x] Validated facts-only endpoint; separate transaction/payment; deterministic rules and policy with explicit provenance.
- [x] Atomic PostgreSQL persistence and idempotency; normalized fingerprint, safe replay, 409 conflicts, rollback, and concurrent uniqueness.
- [x] Injected UUID/time; commit-before-success; no synthetic decision on database failure.
- [x] Decision-only readiness with schema checks; process-only liveness; engine lifecycle and disposal; explicit migrations.
- [x] Compose Decision API → PostgreSQL only; Investigator API has no dependency; no Redis/Kafka application code, ML, or LLM.
- [x] Migration, pure/integration tests, outage/recovery exercise, documentation, and final stack shutdown completed.
- [x] Implementation and report commits, push, remote HEAD, and clean worktree verification follow this report's creation.

## Architecture / invariants check
Master reference preserved. PostgreSQL is authoritative; Redis and Kafka remain outside the Phase-1 decision path. No ADR or deliberate deviation.

## Git
- Branch: `main`.
- Implementation commit: `954944946b3d072ff5220c997f5920af48d42eed`.
- Report commit: this report's commit; see final handoff for SHA.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verify after commit.
- Final `git status`: pending post-push verification.

## Resource / usage notes
The Compose application image was rebuilt twice because source changed after the first outage exercise. Future checkpoints can avoid this by finalizing source before the failure campaign. No new direct runtime dependency or persistent service was introduced.

## Risks / technical debt
Rule set publication/version discipline remains manual. Idempotency entries have no expiration or cleanup, as scoped for CP05. The existing Starlette/AnyIO warning remains.

## Next recommended checkpoint
Phase 1 review/closure: independently verify the deterministic API, PostgreSQL authority, operational failure behavior, and checkpoint evidence. Do not begin Phase 2 event publishing during review.

## Handoff notes for ChatGPT
Review the deferred-FK idempotency claim and concurrency test, commit-before-response boundary, and outage evidence. The saved report cannot attest to its own push; use the final handoff for report SHA, remote HEAD, and clean worktree confirmation.
