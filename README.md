# Argus

Argus is a portfolio project for real-time fraud and trust decisioning with
human investigation support. Deterministic rules and predictive ML may take
part in critical decisions. Generative AI runs asynchronously to help
investigators and is never required for decision availability or correctness.

**Current status:** Phase 0 / Checkpoint 01 repository bootstrap. This
repository currently contains Python tooling and an importable package only;
no decision service or infrastructure has been implemented. See
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
