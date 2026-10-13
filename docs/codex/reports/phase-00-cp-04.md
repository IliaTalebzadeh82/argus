# Phase 00 / Checkpoint 04 — Base event envelope

## Status
`PASS`

## Objective
Define a broker-independent, typed base event envelope and its JSON and schema
semantics without introducing domain events or transport code.

## Implemented
- Added a frozen Pydantic generic `EventEnvelope[PayloadT]` with explicit UUID
  identity, required metadata, typed payload, UTC timestamps, and forbidden
  unknown envelope fields.
- Declared Pydantic 2.x as a direct runtime dependency and updated the lockfile.
- Added event contract documentation and focused unit/contract tests.

## Key decisions
- Producers supply `event_id`; retries and redelivery preserve the logical
  identity. There is no event factory or generated default.
- `occurred_at` and `produced_at` require offsets and normalize to UTC; no
  ordering constraint exists between them.
- `(event_type, event_version)` identifies a stable contract. Breaking changes
  require a new version. `trace_id` and `subject_id` remain opaque strings.
- Envelope freezing is shallow; payload models govern their own mutability.

## Files changed
- Contract: `src/argus/events/__init__.py`, `src/argus/events/envelope.py`.
- Dependency: `pyproject.toml`, `uv.lock`.
- Tests: `tests/unit/test_event_envelope.py`,
  `tests/contract/test_event_envelope_contract.py`.
- Documentation: `docs/architecture/event-contract.md`.

## Validation
- `uv lock && uv sync --locked`: passed; 24 packages resolved. Final direct
  runtime dependencies: FastAPI 0.129.2, Pydantic 2.14.1, Uvicorn 0.54.0.
- `uv run --locked pytest tests/unit/test_event_envelope.py tests/contract/test_event_envelope_contract.py`:
  15 passed. Covers typed construction/JSON round trip, invalid required fields,
  missing identity, unknown field, frozen envelope, retry identity, UTC offset
  normalization, and production time preceding event time.
- `make check`: Ruff lint/format passed; 18 tests passed, one upstream
  Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed. `compose.yaml` did not change.
- `git diff --check`: passed.
- Initial `make check` found Ruff generic syntax, UTC alias, and line length
  issues. Fixed them; final `make check` passed.

## Acceptance criteria
- [x] Reusable broker-independent typed envelope with explicit UUID identity,
  required non-empty identifiers, positive version, and typed payload.
- [x] Aware UTC timestamps; no production/event-time ordering restriction.
- [x] Frozen envelope, rejected unknown fields, validated JSON round trip.
- [x] Contract failure and distributed-system semantics tests; documentation.
- [x] Direct Pydantic dependency; no Kafka client, domain payloads, topic, or
  partitioning decision. Existing APIs and Compose unchanged.
- [x] Required validation passed; implementation and report commits created.
- [x] Push and remote/clean-state verification are recorded in the final
  response after this report commit.

## Architecture / invariants check
The master reference is preserved. PostgreSQL authority, at-least-once delivery,
and critical-path isolation are unchanged. No ADR or deliberate deviation.

## Git
- Branch: `main`.
- Implementation commit: `d88706a148bed2cecfd42d2adcf9ef81e898ca18`.
- Report commit: this report's commit; see `git log -1 --format=%H`.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation.
- Final `git status`: pending post-push verification.

## Resource / usage notes
No Docker stack startup or rebuild was needed. Validation used 15 focused tests
and one passing full `make check` after Ruff corrections.

## Risks / technical debt
Nested mutable payload values remain mutable unless their payload model enforces
immutability. Consumer deduplication and schema migration are later work.

## Next recommended checkpoint
Proceed only to the next separately specified Phase 0 checkpoint; keep transport
and domain behavior outside this base contract.

## Handoff notes for ChatGPT
The saved report cannot attest to its own push. Review the final Codex response
for remote HEAD and clean worktree verification.
