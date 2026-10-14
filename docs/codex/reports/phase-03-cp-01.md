# Phase 03 / Checkpoint 01 — Deterministic simulation kernel

## Status
`PASS`

## Objective
Establish a pure, reproducible simulation foundation without implementing synthetic behavior or infrastructure adapters.

## Implemented
- Added immutable configuration, a virtual UTC clock, simulator-owned named random streams, deterministic identity counters, one-based simulation records, and an immutable canonical JSON manifest.
- Added a toy kernel fixture and eight focused offline contract tests.
- Documented the reproducibility boundary and simulation concepts in `docs/architecture/simulation-kernel.md`.

## Key decisions
- Simulator version **1**; an incompatible generation-semantic change requires a version increment. Reproducibility is scoped to the declared Python 3.13 runtime and locked project environment, not arbitrary future Python PRNG versions.
- Master seed is a required actual integer (including zero/negative; bool rejected). A named stream uses `int(SHA-256(UTF-8(decimal seed + ":" + namespace)))` as its seed; repeated lookup returns the same stateful stream. Other streams cannot shift its state.
- Clock starts at an aware timestamp normalized to UTC; only explicit nonnegative `timedelta` advancement changes it. Zero advancement is accepted.
- IDs use independent kind counters and minimum six-digit padding, e.g. `user-000001`; IDs depend on allocation order, not seed. Records start at sequence **1**.
- `generated_at` captures virtual generation time and does not overwrite an eventual event's `occurred_at`.

## Files changed
- Kernel: `src/argus/simulation/{__init__,config,random,clock,ids,kernel}.py`.
- Tests: `tests/unit/test_simulation_kernel.py`.
- Architecture: `docs/architecture/simulation-kernel.md`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 33 resolved, 31 checked.
- `uv run --locked pytest tests/unit/test_simulation_kernel.py -q`: **8 passed**.
- `make check`: Ruff lint/format passed; **184 offline tests passed**, one existing upstream Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed; no Compose changes or startup.
- `git diff --check` and `git diff --cached --check`: passed.
- First `make check` flagged Ruff UP012 on an explicit UTF-8 `encode` argument. Removed the redundant argument; focused and full checks passed on rerun.

## Acceptance criteria
- [x] Explicit immutable config with validated seed and aware UTC start; no hidden entropy or wall clock.
- [x] Simulator-owned persistent named streams with SHA-256 derivation, repeat semantics, and locality tests.
- [x] Explicit clock, deterministic IDs, one-based sequence, immutable records, and canonical manifest with version 1.
- [x] Toy scenario reproduces records; seed and time dimensions tested separately.
- [x] No unordered output dependency, infrastructure I/O, behavior models, ML, LLM, or new dependency.
- [x] Architecture documentation, focused tests, full offline checks, and Compose validation completed.
- [x] Implementation committed. Report commit, push, remote verification, and clean-status checks follow report creation.

## Architecture / invariants check
Master reference preserved. No ADR or deliberate architectural deviation. Production events, decision logic, PostgreSQL authority, and at-least-once feature processing are unchanged. Simulation code has no Kafka, Redis, PostgreSQL, HTTP, ML, or LLM coupling.

## Git
- Branch: `main`.
- Implementation commit: `96c38bfee6908da156fb321f2bc944451ce1e1ce` (`phase-03/cp-01: add deterministic simulation kernel`).
- Report commit: this report's commit; SHA supplied in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending at report creation; final handoff verifies it.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Only offline checks and Compose configuration validation ran. No containers were started. No token estimate is available.

## Risks / technical debt
`random.Random` output is scoped to the supported runtime, and arbitrary record values are not deeply frozen. The manifest is not a resume snapshot. These boundaries are explicit.

## Next recommended checkpoint
Define initial synthetic-world behavior under a separate Phase 3 checkpoint, using the kernel's explicit stream, time, identity, and record conventions.

## Handoff notes for ChatGPT
The eight focused tests cover the named-stream locality, identity, clock, manifest, and reproducibility contracts. IDs intentionally remain the same across different seeds for the same allocation order; random-dependent values change.
