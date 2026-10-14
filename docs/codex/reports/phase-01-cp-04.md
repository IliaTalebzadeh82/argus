# Phase 01 / Checkpoint 04 — PostgreSQL authority and decision audit persistence

## Status
`PASS`

## Objective
Persist and reconstruct complete Phase-1 deterministic decision records in PostgreSQL without connecting the Decision API yet.

## Implemented
- Added SQLAlchemy Core schema, explicit engine factory, immutable `DecisionRecord`, and insert-only repository with caller-owned atomic transactions.
- Added Alembic migration `09fc42332bec` for 10 relational tables, including ordered context/evaluation/evidence/reason children and typed scalar JSONB signals.
- Added four real PostgreSQL integration tests and three pure record tests; updated local tooling and architecture documentation.

## Key decisions
- Domain snapshots stay independent of SQLAlchemy; repository mapping rehydrates through domain validation.
- Shared facts use insert/reuse/conflict semantics. Decisions use unique insert-only identity; duplicate IDs fail. A decision references the specific payment attempt through a composite foreign key.
- Ordinals and explicit `ORDER BY` preserve all five ordered tuples. Evidence is copied per evaluation; all context signals are retained, including nonmatches.
- SQLAlchemy and Psycopg are runtime dependencies; Alembic is in the development group and excluded from the API runtime image. No Compose change.

## Files changed
- Persistence: `src/argus/persistence/`, `migrations/`, `alembic.ini`.
- Dependencies/tooling: `pyproject.toml`, `uv.lock`, `Makefile`.
- Tests: `tests/integration/test_postgres_decision_repository.py`, `tests/unit/test_decision_record.py`.
- Documentation: `docs/architecture/postgres-persistence.md`, `docs/architecture/local-infrastructure.md`, `README.md`; this report.

## Validation
- `uv sync --locked`: passed. Resolved SQLAlchemy 2.1.4, Psycopg 3.3.6, Alembic 1.20.0.
- `docker compose config --quiet`, `make infra-up`, `docker compose up -d --wait --wait-timeout 120`: passed; all five services healthy.
- `alembic upgrade head; alembic current; alembic downgrade base; alembic upgrade head; alembic check` with host `ARGUS_DATABASE_URL`: passed; current revision `09fc42332bec (head)`, no drift. Downgrade/upgrade was performed only on the disposable local schema.
- `make test-integration`: 4 passed against PostgreSQL, including committed cross-connection reconstruction, exact scalar types/order, shared-fact reuse, duplicate decision rejection, and savepoint rollback after a late fact conflict. All 10 domain/audit tables were empty after tests.
- `make check`: Ruff lint/format passed; 140 offline tests passed, one existing Starlette/AnyIO deprecation warning.
- `git diff --check` and `git diff --cached --check`: passed. `make infra-down`: passed; `docker compose ps` empty, named volumes retained.
- Initial integration run found a test cleanup transaction error; corrected the test to use a savepoint and reran successfully. No production failure remained.

## Acceptance criteria
- [x] Dependencies, Alembic initial migration, clean upgrade, downgrade/re-upgrade, and drift check.
- [x] Domain separation, explicit engine construction, coherent immutable record, and caller-owned atomic write.
- [x] Authoritative shared facts, specific payment, complete decision context, ordered evaluations/evidence/reasons, exact scalar types, and full historical round trip.
- [x] Shared immutable fact reuse/conflict and duplicate decision identity tested; rollback tested against real PostgreSQL.
- [x] Offline tests remain independent of Docker; API remains liveness-only; no Redis/Kafka/ML/LLM wiring or Compose change.
- [x] Documentation, implementation commit, stack shutdown, and validation complete. Report commit/push verification follows this report's creation.

## Architecture / invariants check
Master reference preserved: PostgreSQL authoritative, deterministic decision critical path, immutable history, and attributable evidence. No ADR or deliberate deviation. Phase-1 records contain no ML/model/feature/LLM placeholders.

## Git
- Branch: `main`.
- Implementation commit: `143b4b900837891ff033052f4145782a6cf84976`.
- Report commit: this report's commit; see final handoff for SHA.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verify after commit.
- Final `git status`: pending post-push verification.

## Resource / usage notes
No API image rebuild was needed. The existing five-service Compose stack was started once and stopped after validation. No measured token count is available.

## Risks / technical debt
HTTP persistence failure semantics and API idempotency are deferred to CP05. The existing Starlette/AnyIO deprecation warning remains.

## Next recommended checkpoint
Phase 01 / Checkpoint 05 should wire the Decision API to the repository with explicit database startup/readiness and request failure behavior, while preserving the deterministic rule/policy boundary.

## Handoff notes for ChatGPT
Review migration revision `09fc42332bec`, the repository transaction boundary, four PostgreSQL integration tests, and the absence of API database wiring. The saved report cannot attest to its own push; use the final handoff for report SHA, remote HEAD, and clean worktree confirmation.
