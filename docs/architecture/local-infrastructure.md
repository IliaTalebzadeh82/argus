# Local infrastructure

`compose.yaml` runs three development dependencies, two APIs, a one-shot
`kafka-init` service, and a feature worker. Decision API depends on PostgreSQL
and checks readiness against its decision schema; Investigator API remains liveness-only. Run `make infra-up`,
`make infra-ps`, and `make infra-check`; stop with `make infra-down`.

## State roles

| Service | Intended role | Local persistence |
|---|---|---|
| PostgreSQL | Authoritative Phase-1 transactional and decision audit state | `postgres_data` named volume |
| Redis | Argus online feature projection; derived and rebuildable | No named volume; snapshots and AOF disabled |
| Kafka | Event transport and replay/integration boundary, not the transactional source of truth | `kafka_data` named volume |

Kafka is a single process with both broker and KRaft controller roles. The
controller manages cluster metadata; the broker serves client requests and
stores partition logs. This is a one-node development cluster, so it has no
broker redundancy. The fixed `CLUSTER_ID` identifies this disposable local
cluster when its volume is initialized; retain the same ID when restarting it
with the existing volume.

## Network model

| Dependency | Host process | Future container on the Compose network |
|---|---|---|
| PostgreSQL | `localhost:5432` | `postgres:5432` |
| Redis | `localhost:6379` | `redis:6379` |
| Kafka | `localhost:9092` (EXTERNAL) | `kafka:19092` (INTERNAL) |

Host ports bind to `127.0.0.1` only. Compose provides service-name DNS to
containers on its network. Kafka also listens on `kafka:29093` for controller
traffic; this listener is neither a client endpoint nor exposed to the host.
Kafka advertises `localhost:9092` to host clients and `kafka:19092` to
container clients. A Kafka client first connects to a bootstrap address and
then uses the broker addresses returned in metadata. A container bootstrapping
through the external listener would receive `localhost:9092`, which points
back to itself, so it must use the internal listener.

All three services use plaintext connections and disposable local credentials.
The default PostgreSQL database and user are `argus`; the default password is
`argus_dev_only`. Set `POSTGRES_PASSWORD` in a local ignored `.env` file if
desired. PostgreSQL reads the password only on first initialization of a new
volume, so changing it later does not rotate the existing database password.
These settings are for local development only.

## Dependency failure behavior

Decision API returns HTTP 503 on PostgreSQL connection failure and stays live
but unready. Its engine uses the default pool with `pool_pre_ping` to discard
stale connections after recovery. Migrations run explicitly before the API is
ready. The container healthcheck targets `/health/ready`.

## Initial failure questions

The Compose health checks establish dependency responsiveness, not application
failure policy. Future application code must decide the following before it
depends on these services:

| Dependency | Unavailability, retries, and stale state to decide |
|---|---|
| PostgreSQL | An authoritative read/write failure cannot be treated as a successful transaction. Define request behavior, retryable errors, idempotent writes, and whether any stale read is acceptable. |
| Redis | Derived values can be unavailable, missing, or stale. Define whether to recompute, bypass, or fail each operation; set freshness and retry limits. Redis loss must not silently become loss of authoritative truth. |
| Kafka | Publishing/consuming can be delayed or unavailable. Define retry, replay, ordering, lag, and duplicate handling at each future boundary; assume at-least-once delivery rather than exactly-once consumers. Do not equate a healthy broker with completed downstream work. |

The Decision API service commits the audit and idempotency claim together.
It does not retry writes inside a request.

The feature worker depends on `kafka-init` completing successfully and on healthy
Redis; it has no PostgreSQL dependency. `kafka-init` verifies the three-partition
fraud topic with `retention.ms=-1`, and broker auto-topic creation is disabled.
Infinite retention supports exact replay at the cost of unbounded Kafka disk
growth. The Redis projection is non-authoritative; [redis-feature-projection.md](redis-feature-projection.md)
describes its lifecycle. Redis loss makes features unavailable until replay and
explicit readiness. Decision API still depends only on PostgreSQL.

## Persistence and resource limits

`docker compose down` stops and removes containers and the Compose network but
keeps the PostgreSQL and Kafka named volumes. `make infra-down` uses this
non-destructive command. `docker compose down -v` also removes those volumes
and irreversibly deletes their local data. The Redis image may create an
anonymous `/data` volume, but snapshots and AOF are disabled, so Redis state is
intentionally lost when its container is recreated. All three containers have
memory and CPU limits: PostgreSQL 2 GiB / 2 CPUs, Redis 512 MiB / 1 CPU, and
Kafka 2 GiB / 2 CPUs. Redis also has a 384 MiB key-memory limit with `noeviction`;
Kafka's JVM heap is capped at 1 GiB.
