# Argus — Phase 0 / Checkpoint 01 Prompt

Execute **Phase 0 / Checkpoint 01: repository bootstrap and engineering contract** only.

Read:
- `AGENTS.md`
- `docs/codex/CHECKPOINT_PROTOCOL.md`
- `docs/codex/USAGE_POLICY.md`
- `ARGUS_MASTER_REFERENCE.md` sections 1, 4, 5, 7, 8, 30, 31, 32/Phase 0, 34-36, and 39-40.

Do not implement later Phase 0 infrastructure yet.

## Objective

Turn this starter folder into a clean, reproducible Python repository with the minimum tooling and Git/GitHub foundation needed for the rest of Argus.

## Assumptions

- This is intended to become a public portfolio repository.
- Repository name: `argus`.
- Primary branch: `main`.
- Python target: 3.13+.
- Prefer `uv` for local Python dependency/project management if available and suitable; if not, choose the simplest current alternative and document the reason.
- Do not add FastAPI, database clients, Kafka clients, Redis clients, ML, or LLM dependencies in this checkpoint.

## In scope

1. Inspect the starter files and preserve them.
2. Initialize Git if needed.
3. Create the minimal Python project metadata/tooling:
   - `pyproject.toml`
   - source package skeleton sufficient for import/testing
   - pytest setup
   - Ruff configuration
   - `.gitignore`
4. Create only the repository directories from the master reference that are useful to establish now; do not create meaningless placeholder files across every future subsystem.
5. Add:
   - concise `README.md` describing Argus thesis and current status;
   - `docs/adr/ADR-000-template.md`;
   - any tiny bootstrap docs/scripts needed for reproducible setup.
6. Provide Makefile or equivalent thin command surface for at least:
   - setup/sync
   - lint
   - test
   - check
   Keep it small and non-magical.
7. Verify the project works from a clean dependency sync/install:
   - package imports;
   - at least one meaningful bootstrap test;
   - lint;
   - tests.
8. GitHub:
   - inspect `gh --version` and `gh auth status`;
   - if authenticated and no `origin` exists, create `argus` under the authenticated account as a **public** repository and set `origin`;
   - if `origin` already exists, preserve it;
   - do not alter unrelated global Git/GitHub configuration.
9. Complete the checkpoint Git/report/push protocol.

## Out of scope

Do NOT yet add or run:
- PostgreSQL;
- Redis;
- Kafka/Redpanda;
- Docker Compose infrastructure;
- FastAPI services;
- event envelope implementation;
- Alembic;
- predictive ML;
- LLM tooling.

Those belong to later Phase 0 checkpoints or phases.

## Acceptance criteria

- Python project bootstraps reproducibly.
- `lint`, `test`, and aggregate `check` commands pass.
- No unnecessary runtime dependencies exist.
- README correctly preserves Argus's deterministic-critical-path / async-LLM thesis.
- ADR template exists.
- Git history is clean and checkpoint-scoped.
- GitHub `origin` exists and both checkpoint commits are pushed, unless an external authentication/permission blocker is reported precisely.
- Worktree is clean.
- `docs/codex/reports/phase-00-cp-01.md` exists.
- No Phase 0 infrastructure beyond repository/tooling bootstrap has been implemented.

## Stop condition

Once all acceptance criteria are satisfied (or a concrete external blocker prevents one), write the checkpoint report, commit/push according to the protocol, give the final report using `REPORT_TEMPLATE.md`, and **stop**. Do not begin Checkpoint 02.
