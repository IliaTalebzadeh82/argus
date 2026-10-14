# Phase 02 / Checkpoint 04 — Decision API online feature integration

## Status
`PASS`

## Objective
Make new deterministic payment decisions from caller facts and Redis online features, while preserving PostgreSQL audit truth and replay availability.

## Implemented
- Replaced the HTTP context request with closed, facts-only `facts`, including explicit validated `observed_device_id`; callers cannot provide signals or versions.
- Added the narrow feature-reader dependency, Redis signal adaptation, and event-time lookup at `payment_attempt.attempted_at`. Missing device omits its signal.
- Preserved PostgreSQL claim-before-read idempotency, rollback on feature failure, and Redis-free completed replay. Added 503 `FEATURES_UNAVAILABLE` and Redis-aware readiness.
- Wired Redis into lifespan and Compose, updated architecture and local docs, and added offline and real PostgreSQL/Redis coverage.

## Key decisions
- Signal source is `redis_features_v1`; deployed rule-set version is 2. Rule implementation versions and policy version remain 1.
- PostgreSQL transaction stays open while Redis is read to serialize concurrent keys; there is no distributed transaction. Redis READY proves lifecycle/queryability, not zero Kafka lag or complete late event arrival.
- Generated signals are copied into PostgreSQL `DecisionRecord`, preserving exact historical evidence after Redis changes or loss.

## Files changed
- API/service: `src/argus/apps/decision_api/main.py`, `service.py`; Compose: `compose.yaml`.
- Tests: `tests/unit/test_decision_api.py`, `tests/integration/test_decision_api.py`, `tests/test_app_health.py`.
- Docs: `docs/architecture/decision-api.md`, `redis-feature-projection.md`, `local-infrastructure.md`, `README.md`.

## Validation
- `uv sync --locked`: passed, 33 packages resolved and 31 checked.
- `make check`: Ruff lint/format passed; **170 offline tests passed**, one existing Starlette/AnyIO deprecation warning.
- `ARGUS_DATABASE_URL=postgresql+psycopg://argus:argus_dev_only@localhost:5432/argus ARGUS_REDIS_URL=redis://localhost:6379/0 uv run --locked pytest tests/integration/test_decision_api.py -q`: **4 passed** against real migrated PostgreSQL and Redis.
- `docker compose config --quiet`, `git diff --check`, `git diff --cached --check`: passed.
- `docker compose up -d --build`, `alembic upgrade head`: complete stack started, topic initialized, worker running, PostgreSQL migrated, Redis READY, Decision API ready.
- Real HTTP/Kafka campaign: healthy live/ready **200/200**, ALLOW **200**, Kafka-projected CHALLENGE **200**, replay **200**, changed-facts same-key **409**. Redis stopped without API restart: live/ready/new POST **200/503/503 FEATURES_UNAVAILABLE**, prior replay **200**. Redis recreated with worker stopped: live/ready/new POST **200/503/503** in UNINITIALIZED state. Worker restarted and replayed Kafka: ready **200**, new POST **200 ALLOW**, without API restart.
- Final `make check`: **170 passed**. `docker compose down`; `docker compose ps` empty.
- Initial focused offline run failed because liveness fixture lacked new required Redis URL; updated fixture and reran successfully. An initial docs edit command used unavailable `python`; reran with `uv run --locked python`. No application failure remained.

## Acceptance criteria
- [x] Facts-only closed request, explicit observed-device validation, no caller signal override.
- [x] Redis event-time snapshot produces durable source-tagged signals; missing device is business REVIEW, READY zeros are valid.
- [x] Rule-set 2, unchanged rule/policy versions; no historical migration.
- [x] Claim-before-feature-read, replay without Redis, changed-request conflict, and failed-read rollback.
- [x] 503 feature availability, distinct database error, process-only liveness, PostgreSQL plus Redis readiness.
- [x] Compose Redis dependency and no direct Decision API Kafka dependency.
- [x] Offline, focused integration, runtime outage/rebuild, final checks, and stack teardown passed.

## Architecture / invariants check
Master reference preserved: PostgreSQL is authoritative, Redis is derived, Kafka stays behind the worker, and decisions use deterministic rules. No ADR, migration, Kafka topic/schema change, ML/LLM work, or deliberate deviation.

## Git
- Branch: `main`.
- Implementation commit: `06b401301223fc655b84d724a70981eb1b6beb41`.
- Report commit: this report's commit; SHA in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; verified in final handoff.
- Final `git status`: pending post-push verification.

## Resource / usage notes
The complete Compose build and live outage/rebuild campaign were run once. No measured token or performance metric is available.

## Risks / technical debt
READY does not measure Kafka lag or certify all late event-time facts have arrived. The PostgreSQL transaction is held during the Redis read. These are explicit CP04 limits for later evaluation.

## Next recommended checkpoint
Phase 02 / Checkpoint 05 should measure lag and freshness failure behavior using the current boundary, then decide whether stronger readiness or freshness guarantees are warranted.

## Handoff notes for ChatGPT
Review the facts-only fingerprint and claim-before-Redis order in `service.py`, stored generated signals in the integration test, and the live outage/rebuild observations above. Final response supplies report SHA, remote HEAD, and clean-worktree confirmation.
