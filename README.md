# Argus

Argus is a portfolio project for real-time fraud and trust decisioning with
human investigation support. Deterministic rules and predictive ML may take
part in critical decisions. Generative AI runs asynchronously to help
investigators and is never required for decision availability or correctness.

**Current status:** Phase 0 complete — foundation and architecture established.
Phase 1 core fraud domain is next. This repository currently contains two
liveness-only APIs, a base event contract, and a local PostgreSQL/Redis/Kafka
Compose stack. See
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

Run one API on the host in its own terminal with `make decision-api` or
`make investigator-api`. They listen on `127.0.0.1:8001` and
`127.0.0.1:8002` respectively. Set `ARGUS_HOST`, `ARGUS_PORT`, or
`ARGUS_LOG_LEVEL` to override a process default.

## Local infrastructure

Install Docker with the Compose plugin, then run:

```sh
make infra-up     # start PostgreSQL, Redis, Kafka, and both APIs
make infra-ps     # show container health
make infra-check  # query all three dependencies
make infra-down   # stop, retaining PostgreSQL and Kafka volumes
```

The APIs expose `/health/live` on ports 8001 and 8002. See
[application boundaries](docs/architecture/application-boundaries.md) for
their responsibilities and current dependency graph.

The PostgreSQL default password is `argus_dev_only`, for disposable local
development only. Copy `.env.example` to `.env` to override it before first
startup. See [local infrastructure](docs/architecture/local-infrastructure.md)
for endpoints, state roles, and volume behavior.
