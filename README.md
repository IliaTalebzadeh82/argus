# Argus

Argus is a portfolio project for real-time fraud and trust decisioning with
human investigation support. Deterministic rules and predictive ML may take
part in critical decisions. Generative AI runs asynchronously to help
investigators and is never required for decision availability or correctness.

**Current status:** Phase 2 complete — typed fraud events flow through
at-least-once Kafka processing into rebuildable Redis online features that
feed the deterministic Decision API. Freshness is eventually consistent:
Redis `READY` does not imply zero Kafka lag or event-time completeness.
PostgreSQL remains authoritative for decisions and audit. Phase 3 is next.
The Investigator API remains liveness-only. See
[`ARGUS_MASTER_REFERENCE.md`](ARGUS_MASTER_REFERENCE.md) for the architecture
and phase plan.

## Local setup

Install [uv](https://docs.astral.sh/uv/) and use Python 3.13 or newer.
The checked-in `.python-version` selects Python 3.13 when available.

```sh
make setup  # install the package and development tools from uv.lock
make lint   # Ruff lint and format check
make test   # pytest
make check  # lint and test
```

`make sync` is an alias for `make setup`. Dependencies are locked in `uv.lock`.

Set `ARGUS_DATABASE_URL` and `ARGUS_REDIS_URL` for the Decision API before starting it on the host;
the default local value is
`postgresql+psycopg://argus:argus_dev_only@localhost:5432/argus`. Compose uses
`postgresql+psycopg://argus:${POSTGRES_PASSWORD:-argus_dev_only}@postgres:5432/argus`.
Use `ARGUS_REDIS_URL=redis://localhost:6379/0` on the host. Run migrations explicitly with `make db-upgrade`; readiness also requires a READY Redis projection.

Run one API on the host in its own terminal with `make decision-api` or
`make investigator-api`. They listen on `127.0.0.1:8001` and
`127.0.0.1:8002` respectively. Set `ARGUS_HOST`, `ARGUS_PORT`, or
`ARGUS_LOG_LEVEL` to override a process default.

## Local infrastructure

Install Docker with the Compose plugin, then run:

```sh
make infra-up     # start dependencies, topic init, feature worker, and APIs
make infra-ps     # show container health
make infra-check  # query all three dependencies
make infra-down   # stop, retaining PostgreSQL and Kafka volumes
```

Both APIs expose `/health/live`; Decision API also exposes `/health/ready`
and `POST /v1/decisions/payment` on port 8001. See
[application boundaries](docs/architecture/application-boundaries.md) for
their responsibilities and current dependency graph.

The PostgreSQL default password is `argus_dev_only`, for disposable local
development only. Copy `.env.example` to `.env` to override it before first
startup. See [local infrastructure](docs/architecture/local-infrastructure.md)
for endpoints, state roles, and volume behavior.

Phase-1 PostgreSQL audit work on the host:

```sh
export ARGUS_DATABASE_URL=postgresql+psycopg://argus:argus_dev_only@localhost:5432/argus
make infra-up
make db-upgrade
make db-current
make test-integration
make infra-down
```

`make check` runs pure and API tests without PostgreSQL. Use the local password
shown above only with the disposable default Compose database.

Phase-2 Kafka/Redis commands (use explicit host endpoints):

```sh
export ARGUS_KAFKA_BOOTSTRAP_SERVERS=localhost:9092
export ARGUS_REDIS_URL=redis://localhost:6379/0
make kafka-init               # create/verify the fraud topic
make feature-worker           # host-side Kafka -> Redis worker
make test-kafka-integration   # focused real Kafka + Redis checks
make feature-lag              # operator-only live group offset/backlog snapshot
make test-phase02-failures    # real failure campaign; also set ARGUS_DATABASE_URL
```

Compose also runs `kafka-init` and `feature-worker`. See
[Kafka feature worker](docs/architecture/kafka-feature-worker.md) for transport
and replay semantics.

### Phase 03 demo workload

```bash
uv run --locked python -m argus.simulation.cli export --spec configs/simulation/phase-03-demo.json --output /tmp/argus-phase03
uv run --locked python -m argus.simulation.cli publish --spec configs/simulation/phase-03-demo.json --bootstrap-servers localhost:9092 --topic argus.fraud-events.v1 --unpaced
```

Export needs no services; publication needs Kafka. See [simulation adapters](docs/architecture/simulation-adapters.md).
