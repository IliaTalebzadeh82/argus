# Phase 00 / Checkpoint 02 — Local distributed infrastructure

## Status
`PASS`

## Objective
Establish a reproducible, health-checkable local PostgreSQL, Redis, and
single-node Kafka KRaft stack without application services.

## Implemented
- Added a three-service `compose.yaml` with versioned images, native health
  checks, loopback host ports, resource limits, and PostgreSQL/Kafka named volumes.
- Added `make infra-up`, `infra-down`, `infra-ps`, and `infra-check`.
- Documented state ownership, host/container endpoints, persistence, and open
  dependency-failure decisions; updated README and local password example.

## Key decisions
- Images: `postgres:17.11`, `redis:7.2.16`, `apache/kafka:4.3.1`.
- Kafka combines broker and controller roles in one KRaft node. Its INTERNAL
  listener advertises `kafka:19092`; EXTERNAL advertises `localhost:9092`.
- PostgreSQL and Kafka retain named volumes on `docker compose down`. Redis is
  derived state with snapshots and AOF disabled. The default PostgreSQL password
  is explicitly disposable development-only; `.env` is ignored.
- Limits: PostgreSQL 2 GiB / 2 CPUs, Redis 512 MiB / 1 CPU (384 MiB key memory),
  Kafka 2 GiB / 2 CPUs (1 GiB JVM heap).

## Files changed
- Infrastructure: `compose.yaml`, `.env.example`, `.gitignore`, `Makefile`.
- Documentation: `docs/architecture/local-infrastructure.md`, `README.md`.

## Validation
- `docker compose config --quiet` and `docker compose config --services`:
  passed; exactly `kafka`, `postgres`, `redis`.
- `make check`: Ruff lint and format passed; pytest 1 passed.
- `make infra-up`: pulled the three images and started all three containers.
- `make infra-ps`: all three reached `healthy` with loopback-bound host ports.
- `make infra-check`: PostgreSQL `accepting connections`; Redis `PONG`; Kafka
  native topic listing exited 0 with no Argus topics.
- `docker compose exec -T postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT 1"'`:
  returned `1`.
- Kafka broker CLI against `localhost:9092`: exited 0 and reported broker 1
  at `localhost:9092`; internal CLI checks used `kafka:19092`.
- `docker compose restart kafka`, then
  `docker compose up -d --wait --wait-timeout 120`: Kafka returned to `healthy`;
  `make infra-check` passed again. KRaft quorum status showed leader 1 and
  controller endpoint `kafka:29093`.
- `docker stats --no-stream`: captured live container metrics. A later targeted
  idle reading is recorded below.
- `make infra-down`: removed containers and network; `docker compose ps -a`
  showed no services while `argus_postgres_data` and `argus_kafka_data` remained.
- `git diff --cached --check`: passed. No configuration or test failure occurred;
  the initial image pull was slow but completed.

## Acceptance criteria
- [x] Compose validates, has exactly three infrastructure services, and uses
  explicit stable image versions.
- [x] PostgreSQL, Redis, and Kafka KRaft start and become healthy.
- [x] Kafka internal and host listeners are configured and responsive.
- [x] Named persistence, sensible limits, and real response checks exist.
- [x] Existing `make check` passes; no Python runtime dependency, application
  service, domain model, event topic, or event schema was added.
- [x] Architecture and setup documentation cover state roles, networking,
  failure questions, and persistence.
- [x] Implementation commit exists; validation ended with the stack stopped.
- [ ] Report commit, push to `origin/main`, remote HEAD, and clean worktree:
  verify after this report is committed.

## Architecture / invariants check
The master reference is preserved: PostgreSQL is future authoritative state,
Redis is derived state, and Kafka is transport/replay. No ADR or deliberate
deviation was needed.

## Git
- Branch: `main`.
- Implementation commit: `9363c27ae99c75c4e5300598bce5b42abc864d42`.
- Report commit: this report's commit; see `git log -1 --format=%H`.
- Remote: `origin` → `git@github.com:IliaTalebzadeh82/argus.git`.
- Push result: pending at report creation.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Idle `docker stats --no-stream argus-postgres-1 argus-redis-1 argus-kafka-1`
showed PostgreSQL 25.76 MiB / 2 GiB, Redis 4.141 MiB / 512 MiB, and Kafka
287.6 MiB / 2 GiB. The first pull took several minutes; subsequent checkpoints
can reuse these local images.

## Risks / technical debt
The one-node Kafka setup has no broker redundancy and all connections are
plaintext; both are intentional local-development constraints. Application
retry, stale-data, and fallback policies remain future decisions.

## Next recommended checkpoint
Proceed only to the next explicitly assigned Phase 0 checkpoint; do not infer
its application-service scope from this infrastructure work.

## Handoff notes for ChatGPT
The stack is stopped; PostgreSQL and Kafka named volumes remain. The saved
report cannot attest to its own push, so confirm the report commit, remote
`main` HEAD, and clean worktree from the final handoff.
