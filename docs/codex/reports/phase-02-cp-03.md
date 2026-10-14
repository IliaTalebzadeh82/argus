# Phase 02 / Checkpoint 03 — Kafka transport, replay, and feature worker

## Status
`PASS`

## Objective
Connect typed fraud events through Kafka to the Redis feature projection with explicit at-least-once offsets and full-history rebuild after Redis loss.

## Implemented
- Added canonical typed JSON wire handling, user-ID record keys, and an acknowledged idempotent Kafka producer.
- Added deterministic topic provisioning and a one-shot Compose `kafka-init`; local Kafka auto-topic creation is disabled.
- Added a synchronous feature worker that commits the next Kafka offset only after Redis `APPLIED` or `DUPLICATE`, and a separate manual-assignment Kafka rebuild to a captured per-partition cutoff.
- Added Redis lifecycle introspection, 11 real Kafka/Redis integration tests, 7 new offline tests, architecture documentation, and explicit host commands.

## Key decisions
- Topic `argus.fraud-events.v1`: 3 local partitions, RF=1 for one broker, `retention.ms=-1`, `retention.bytes=-1`, delete cleanup. Infinite retention preserves exact replay but grows Kafka disk without bound.
- `payload.user_id` is the Kafka key; envelope `subject_id` retains its own meaning. Per-user ordering is useful, while Redis event-time correctness does not rely on delivery order.
- Live group `argus-feature-projection-v1` disables automatic commit and offset store, starts at earliest without prior commits, and synchronously commits `offset+1`. The observed local broker used the classic group protocol; no rebalance/session tuning was added.
- Rebuild requires low offset zero, ignores live committed offsets, resumes `REBUILDING` by replaying from zero, and marks `READY` only after all captured high offsets are processed. Newer records remain for live consumption.
- Invalid records, identity conflicts, Redis errors, and commit failures fail without committing. Redis errors have unknown write outcome; redelivery is the reconciliation path. Poison policy is deferred.

## Files changed
- Transport and worker: `src/argus/events/kafka.py`, `kafka_admin.py`; `src/argus/workers/`; Redis state API.
- Runtime: `pyproject.toml`, `uv.lock`, `compose.yaml`, `Makefile`.
- Tests: `tests/unit/test_kafka_wire.py`, `test_feature_worker_offsets.py`; `tests/integration/test_kafka_feature_worker.py`.
- Docs: `docs/architecture/kafka-feature-worker.md`, Redis/local infrastructure docs, `README.md`.

## Validation
- `uv lock && uv sync --locked`: passed; `confluent-kafka==2.16.0` resolved. Kafka broker image/CLI version: `4.3.1`.
- `ARGUS_KAFKA_BOOTSTRAP_SERVERS=localhost:9092 ARGUS_REDIS_URL=redis://localhost:6379/0 make test-kafka-integration`: **11 passed**. Topic create/idempotent verify/mismatch rejection; live history and duplicate commits; real apply-before-commit redelivery; simulated lost Redis reply and redelivery; partial rebuild recovery; replay ignoring group offsets; empty rebuild; three poison cases; Redis/commit failure; identity conflict.
- Topic inspection: `kafka-topics.sh --describe --topic argus.fraud-events.v1` showed 3 partitions, RF=1, `retention.ms=-1`. Compose brought up `kafka`, `redis`, `kafka-init` (exit 0), then `feature-worker` (running).
- Redis-loss campaign: published four records to the default topic; before loss and after stopping the worker, recreating Redis, and restarting the worker, the snapshot was `(payments_10m, failed_payments_1h, accounts_on_device)=(1,1,2)`. Kafka replay restored state to `READY`.
- `make check`: Ruff lint/format passed; **168 offline tests passed**, one existing Starlette/AnyIO deprecation warning. `docker compose config --quiet`, `git diff --check`, and `git diff --cached --check`: passed. `docker compose down`; `docker compose ps` empty.
- During iteration, an incremental-config test initially used the wrong Confluent API shape; fixed with `ConfigEntry`, then provisioning and the full 11-test suite passed. Immediately after a Kafka container restart, the first campaign snapshot poll timed out while the prior group member was still being removed; the group stabilized and the snapshot and loss/rebuild checks passed.

## Acceptance criteria
- [x] Five typed wire contracts and deterministic user keys; caller-owned identity; broker-acknowledged producer with idempotence and `acks=all`.
- [x] Explicit topic contract and Compose initialization; no auto-topic creation.
- [x] Real group, manual synchronous next-offset commits after `APPLIED` or `DUPLICATE` only; Redis errors, conflicts, poison, and commit errors do not claim success.
- [x] Real Kafka redelivery after apply-before-commit and unknown Redis outcome converges to one contribution.
- [x] Rebuild from full Kafka history supports empty, interrupted, and Redis-loss cases independent of group offsets; reference-equivalent snapshots across users/partitions.
- [x] Decision/Investigator APIs and PostgreSQL schema unchanged; no outbox, DLQ, ML, or LLM work.
- [x] Offline validation, documentation, Compose teardown, implementation/report commits, push, and remote verification completed at checkpoint handoff.

## Architecture / invariants check
Master reference preserved: PostgreSQL remains decision/audit authority; Kafka is at-least-once transport and Redis is derived. Generative AI is absent from the critical path. No ADR or architectural deviation.

## Git
- Branch: `main`.
- Implementation commit: `e902d029c7d90274d2de8d9063b64d5c4a30e319`.
- Report commit: this report's commit; SHA in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending report commit; verified in final handoff.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Focused Kafka tests took about 47 seconds on the final run; the local Kafka/Redis stack was stopped. No token metric was measured.

## Risks / technical debt
Kafka and Redis feature history remain unbounded; local Kafka RF=1 has no redundancy. Per-message sync commits cost throughput. A poison record blocks its partition, and a new live group may replay history after rebuild. Multi-worker rebalance and failure orchestration remain later work.

## Next recommended checkpoint
Phase 02 / Checkpoint 04 should integrate the existing Redis feature projection into the deterministic Decision API boundary under its own explicit availability and fallback rules.

## Handoff notes for ChatGPT
Review the Kafka offset ordering and cutoff replay in `src/argus/workers/feature_worker.py` against the 11 real integration cases. The report cannot attest to its own push; the final response supplies report SHA, remote HEAD, and clean-worktree confirmation.
