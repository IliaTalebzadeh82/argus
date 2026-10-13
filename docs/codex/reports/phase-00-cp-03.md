# Phase 00 / Checkpoint 03 — Application service skeletons

## Status
`PASS`

## Objective
Establish independent, executable Decision and Investigator API process and
container boundaries without wiring infrastructure or business behavior.

## Implemented
- Added two FastAPI applications with typed `GET /health/live` responses and
  distinct service identities.
- Added environment-configured host entry points, a shared Python 3.13 image,
  Compose services with loopback host ports, liveness health checks, and 512 MiB
  / 0.5 CPU limits each.
- Added focused endpoint tests and application boundary documentation.

## Key decisions
- Each service owns its app and fixed identity. `ARGUS_HOST`, `ARGUS_PORT`, and
  `ARGUS_LOG_LEVEL` configure process execution; host defaults use loopback.
- Only liveness is defined because neither application currently needs an
  external dependency. Compose has no `depends_on` for the APIs.
- FastAPI is constrained below 0.130 because the newer 0.143 release pulled
  OpenTelemetry into the production dependency tree. `httpx` is development
  only for FastAPI's test client. The builder installs pinned `uv` and installs
  only locked production dependencies; the runtime image contains neither
  `uv` nor test tools.

## Files changed
- Runtime and tests: `src/argus/apps/`, `tests/test_app_health.py`,
  `pyproject.toml`, `uv.lock`.
- Containers and commands: `Dockerfile`, `.dockerignore`, `compose.yaml`,
  `Makefile`.
- Documentation: `README.md`, `docs/architecture/application-boundaries.md`,
  `docs/architecture/local-infrastructure.md`.

## Validation
- `uv sync --locked`: passed. `uv tree --no-dev`: direct runtime dependencies
  are FastAPI 0.129.2 and Uvicorn 0.54.0; transitive packages are
  `annotated-doc`, `annotated-types`, `anyio`, `click`, `h11`, `idna`,
  `pydantic`, `pydantic-core`, `starlette`, `typing-extensions`, and
  `typing-inspection`. No PostgreSQL, Redis, Kafka, SQLAlchemy, Alembic, ML,
  LLM, or OpenTelemetry package.
- `make check`: Ruff lint and format passed; pytest 3 passed. One upstream
  Starlette/AnyIO deprecation warning occurred in the test client.
- Host subprocess check: both Python module entry points returned HTTP 200 and
  their exact expected service identity on ports 8001 and 8002.
- `docker compose config --quiet`: passed; exactly five services.
- `make infra-up` then `docker compose up -d --no-build --wait --wait-timeout 120`:
  built both images and all five services reached healthy.
- `make infra-check`: PostgreSQL accepted connections, Redis returned `PONG`,
  Kafka topic listing succeeded.
- Host `curl` to both `/health/live` endpoints returned correct JSON. Requests
  from each API container to the other via Compose service name returned the
  other service's identity.
- `docker stats --no-stream argus-decision-api-1 argus-investigator-api-1`:
  idle Decision API 41.49 MiB / 512 MiB, 0.24% CPU; Investigator API
  43.63 MiB / 512 MiB, 0.23% CPU.
- `docker compose restart decision-api` followed by the wait command: Decision
  API returned healthy and its host endpoint returned correct JSON.
- `make infra-down`: stack stopped; `docker compose ps -a` empty;
  `argus_postgres_data` and `argus_kafka_data` volumes remain.
- First build attempts before VPN restoration stalled on external DNS/download
  of `uv`. The retry with VPN completed; no remaining build failure.

## Acceptance criteria
- [x] Both APIs run on host and in Compose, with tested, distinct liveness.
- [x] Exactly three infrastructure services and two application services;
  meaningful health checks, loopback host exposure, and resource limits.
- [x] No false datastore, broker, or LLM application dependencies.
- [x] Runtime dependency tree is minimal and excludes prohibited clients and
  OpenTelemetry.
- [x] `make check`, Compose validation, startup, DNS, resource inspection,
  restart, and stack shutdown passed.
- [x] Architecture note and README describe current boundaries.
- [x] Implementation and report commits created; push and remote/clean-state
  verification are performed after this report commit.

## Architecture / invariants check
The master reference is preserved. Decision availability does not require an
LLM; no authoritative or derived state responsibilities were changed. No ADR
or deliberate deviation.

## Git
- Branch: `main`.
- Implementation commit: `5b550ea1ec29549d3862e3327aa84a0f2b1f458a`.
- Report commit: this report's commit; see `git log -1 --format=%H`.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation.
- Final `git status`: pending post-push verification.

## Resource / usage notes
First image download was slowed by DNS failure before VPN restoration. The
successful image build installed 14 production packages. Avoid rebuilding for
documentation-only changes; reuse the cached images.

## Risks / technical debt
Liveness does not express future dependency readiness. Add readiness only when
service behavior actually requires an external dependency.

## Next recommended checkpoint
Proceed to the separately specified base event envelope checkpoint. Do not
introduce its schema or producers as part of these service skeletons.

## Handoff notes for ChatGPT
The stack is stopped and named PostgreSQL/Kafka volumes remain. The saved
report cannot attest to its own push; use the final Codex response for remote
HEAD and clean worktree verification.
