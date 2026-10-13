# Phase 00 review — Foundation and Architecture

## 1. What was built?

CP01 established the Python 3.13 package, locked `uv` tooling, Ruff, pytest,
Make targets, Git repository, and ADR template. CP02 added local PostgreSQL,
Redis, and single-node Kafka in Compose. CP03 added independent Decision and
Investigator API processes and containers with liveness endpoints. CP04 added a
typed, broker-independent `EventEnvelope` with unit and contract tests.

The current topology is one local Compose network with five containers:
PostgreSQL, Redis, Kafka, Decision API, and Investigator API. The two APIs have
no application dependency on each other or on those three infrastructure
services. The event envelope is a Python contract; nothing publishes it to
Kafka yet.

## 2. What changed from the master plan?

No material architectural deviation. Apache Kafka is one of the two explicitly
allowed broker choices. The `src/argus` package layout, pinned FastAPI range,
single-node local configuration, and liveness-only APIs are implementation
details consistent with the staged plan. Later repository directories remain
uncreated until needed.

## 3. Why did it change?

Not applicable to architectural deviations. Kafka was selected to exercise its
native operational model. FastAPI was constrained below 0.130 to avoid an
unneeded OpenTelemetry production dependency in Phase 0. Liveness-only services
reflect their current lack of external application dependencies.

## 4. What failed?

Environment/tooling: CP01's first Ruff format check included a fenced Python
example in the master reference; scoping Ruff to `src tests` fixed the tooling
boundary. CP03's first image build stalled on external DNS/download of `uv`;
the retry after VPN restoration succeeded.

Design/implementation: CP04's initial check found Ruff generic syntax, UTC
alias, and line-length issues. Corrections passed the subsequent check. No
unresolved Phase 0 implementation defect appeared in this review. The current
test run has one upstream Starlette/AnyIO deprecation warning.

## 5. What was learned?

**Process and container boundaries.** A shared Compose network supplies DNS
and reachability, not an application dependency. Neither API imports clients
or calls the other API, database, cache, or broker. Dependency and readiness
semantics begin when application behavior relies on an external service.

**Host and container networking.** A host Kafka client uses `localhost:9092`;
a Compose client uses `kafka:19092`. Kafka returns advertised broker addresses
after bootstrap, so a container using the external listener would receive
`localhost:9092`, which points back to that container.

**State ownership.** PostgreSQL is designated the future authoritative
transactional/audit store. Redis is future derived, rebuildable state. Kafka
is transport with replayable logs, not transactional truth. No Argus fraud
domain records exist yet.

**Event semantics.** An event is one logical fact; a message is its transport
representation or delivery. A producer supplies `event_id`, which remains the
same across publish retries and redelivery. Future consumers must handle
duplicates under at-least-once delivery.

**Time semantics.** `occurred_at` is when the fact happened; `produced_at` is
when its integration event was made; consumer processing time is when a
consumer handles a delivery. All may differ. The envelope normalizes the first
two to UTC and does not impose an ordering between them.

**Health semantics.** Liveness says the process responds. Readiness says it can
perform its required work, including real dependencies. Current APIs require no
external service, so a database or broker readiness probe would claim a
dependency that does not exist.

## 6. What metrics were observed?

Current `make check`: Ruff lint passed, 12 files formatted, 18 tests passed,
one upstream deprecation warning. Compose defines five services; all five
reached healthy. A settled, no-load `docker stats --no-stream` snapshot showed:

| Service | Memory use | Configured memory limit |
| --- | ---: | ---: |
| PostgreSQL | 18.55 MiB | 2 GiB |
| Redis | 3.465 MiB | 512 MiB |
| Kafka | 280.7 MiB | 2 GiB |
| Decision API | 41.42 MiB | 512 MiB |
| Investigator API | 42.79 MiB | 512 MiB |

These are local idle snapshots, not throughput or capacity benchmarks.

## 7. What technical debt was introduced?

The one-node Kafka broker has no redundancy. Connections are plaintext, and
the PostgreSQL default password is disposable. These are intentional local
development constraints and must not be carried into a production deployment.
Redis intentionally has no persistence because its assigned role is derived.

The following are deliberate future work, not defects in Phase 0: dependency
readiness once APIs actually use dependencies; consumer deduplication and
partial-failure handling; broker integration; schema migration/upcasting; and
deep immutability where payloads need it. The envelope freezes only its outer
model. The single Starlette/AnyIO warning is a minor dependency maintenance
item, not a failing check.

## 8. Is the next phase still correct?

Yes. Phase 1 should build users, devices, transactions, payments, decisions,
risk signals, a rule engine, a policy engine, and a deterministic Decision API.
The foundation is sufficient to begin that work without ML. This review makes
no Phase 1 design or implementation decision.

## 9. Does the master plan need an ADR/update?

No. Phase 0 selected allowed options and made local implementation choices;
none changes or consequentially narrows the master architecture. No ADR was
created.

## Phase 0 Gate

**Why does each dependency exist?** FastAPI serves the two HTTP API skeletons.
Pydantic validates their response models and the base event envelope. Uvicorn
runs each ASGI application. PostgreSQL is provisioned for future authoritative
transactional/audit state. Redis is provisioned for future derived online
state. Kafka is provisioned for future asynchronous event transport and replay.
The latter three are running local infrastructure, not current API imports or
runtime calls. Direct Python runtime dependencies are exactly FastAPI 0.129.2,
Pydantic 2.14.1, and Uvicorn 0.54.0. No PostgreSQL, Redis, or Kafka Python
client, SQLAlchemy, Alembic, ML, LLM, or OpenTelemetry package is direct.

**Which state is authoritative?** Argus has no fraud-domain application state
yet. PostgreSQL is designated the future authoritative transactional/audit
store. Redis is designated derived/rebuildable. Kafka holds transport/replay
state but is not the transactional source of truth. No Argus domain records
exist yet.

**How do services communicate?** Currently the APIs respond to HTTP liveness
requests. They do not call each other or PostgreSQL, Redis, or Kafka.
`EventEnvelope` is not published anywhere. Compose network reachability alone
does not change this. Future designated boundaries use synchronous HTTP/API
calls where appropriate and Kafka for asynchronous integration/event flow.

## Architecture invariants

- LLM absent from the critical decision path: preserved; no LLM integration.
- PostgreSQL designated authoritative and Redis designated derived: preserved.
- Kafka treated as transport/replay, not transactional truth: preserved.
- At-least-once assumptions retained: preserved; no exactly-once consumer claim.
- Logical event identity separated from delivery identity: preserved by explicit,
  retry-stable `event_id`.
- No premature domain, ML, or LLM implementation: preserved.

## Validation and status

`uv sync --locked`, `make check`, `docker compose config --quiet`, and all five
Compose health checks passed. `make infra-check` returned PostgreSQL accepting
connections, Redis `PONG`, and successful Kafka topic listing. Both host API
liveness requests returned HTTP 200 with the correct service identities.
`make infra-down` left no Argus containers or Compose network, while
`argus_postgres_data` and `argus_kafka_data` remained. No Phase 0 gate or
invariant is blocked.

**Phase status: PASS.**
