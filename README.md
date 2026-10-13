# Argus

Argus is a portfolio project for real-time fraud and trust decisioning with
human investigation support. Deterministic rules and predictive ML may take
part in critical decisions. Generative AI runs asynchronously to help
investigators and is never required for decision availability or correctness.

**Current status:** Phase 0 / Checkpoint 02 local infrastructure. This
repository contains Python tooling, an importable package, and a local
PostgreSQL/Redis/Kafka Compose stack; no application service exists yet. See
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

`make sync` is an alias for `make setup`. The project has no runtime
dependencies. Python tooling is pinned through `uv.lock`.

## Local infrastructure

Install Docker with the Compose plugin, then run:

```sh
make infra-up     # start PostgreSQL, Redis, and Kafka
make infra-ps     # show container health
make infra-check  # query all three dependencies
make infra-down   # stop, retaining PostgreSQL and Kafka volumes
```

The PostgreSQL default password is `argus_dev_only`, for disposable local
development only. Copy `.env.example` to `.env` to override it before first
startup. See [local infrastructure](docs/architecture/local-infrastructure.md)
for endpoints, state roles, and volume behavior.
