# Phase 00 / Checkpoint 01 — Repository bootstrap and engineering contract

## Status
`PASS`

## Objective
Establish a reproducible Python 3.13+ repository with minimal package, test,
lint, documentation, and Git/GitHub foundations.

## Implemented
- Preserved the starter instructions and master reference in a new Argus Git repository.
- Added an importable `argus` package, `pyproject.toml`, `.python-version`,
  `uv.lock`, pytest, Ruff, and a small Makefile.
- Added a bootstrap package-installation test, README, `.gitignore`, and ADR template.
- Created a public GitHub repository and configured `origin`.

## Key decisions
- Initialized Git inside `argus/` because the existing parent Git repository
  also contains unrelated projects and has no commits or remote.
- Used `uv` with a checked-in lockfile. Development tools are the only dependencies;
  no runtime dependencies were added.
- Established only the package, tests, and ADR directories needed now.

## Files changed
- Project and tooling: `.python-version`, `.gitignore`, `pyproject.toml`,
  `uv.lock`, `Makefile`, `src/argus/__init__.py`, `tests/test_bootstrap.py`.
- Documentation: `README.md`, `docs/adr/ADR-000-template.md`.
- Preserved starter files: `.codex/config.toml`, `AGENTS.md`,
  `ARGUS_MASTER_REFERENCE.md`, `FIRST_CODEX_PROMPT.md`, `docs/codex/*`.

## Validation
- `gh --version`: 2.46.0; `gh auth status`: authenticated as
  `IliaTalebzadeh82` with `repo` scope.
- `uv lock`: resolved 8 packages using Python 3.13.15.
- `make setup`: clean `.venv` creation and 7 packages installed, including Argus.
- `uv run --locked python -c 'import argus; from importlib.metadata import version; print(argus.__version__, version("argus"))'`: `0.1.0 0.1.0`.
- First `make check`: Ruff format check on `.` flagged an existing fenced Python
  snippet in the master reference. Scoped Ruff to `src tests`; no starter text changed.
- Final `make check`: Ruff lint passed, Ruff format check passed for 2 files,
  pytest passed (1 test).
- `git diff --cached --check -- . ':!ARGUS_MASTER_REFERENCE.md'`: passed.
  The preserved master reference contains intentional Markdown hard-break spaces.
- `gh repo view IliaTalebzadeh82/argus --json name,visibility,url`:
  confirmed `PUBLIC` at `https://github.com/IliaTalebzadeh82/argus`.

## Acceptance criteria
- [x] Python project bootstraps reproducibly from `uv.lock`.
- [x] `lint`, `test`, and aggregate `check` commands pass.
- [x] No runtime dependencies or later infrastructure added.
- [x] README states the deterministic decision path and asynchronous LLM boundary.
- [x] ADR template and clean, checkpoint-scoped Git history exist.
- [x] Public GitHub `origin` exists.
- [x] Report exists and implementation commit recorded.
- [ ] Both commits pushed and worktree clean (verified after this report commit).

## Architecture / invariants check
Preserved the master reference. No ADR was needed and no architectural deviation
was introduced.

## Git
- Branch: `main`
- Implementation commit: `604a1a37591fc181cdbed0c3037fd14c2a14a820`
- Report commit: this report's commit; see `git log -1 --format=%H`.
- Remote: `origin` → `git@github.com:IliaTalebzadeh82/argus.git`
- Push result: pending at report creation; verify after committing this file.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Initial `make setup` took about 22 seconds to prepare packages. Future checkpoints
can reuse the locked environment and run targeted checks during iteration.

## Risks / technical debt
None within this checkpoint.

## Next recommended checkpoint
Proceed to the next explicitly assigned Phase 0 checkpoint. Do not add
infrastructure until its scope and acceptance criteria are provided.

## Handoff notes for ChatGPT
The first repository commit includes the preserved starter documents because
the new Argus Git repository began with no history. The parent directory's
unrelated projects were not changed. Confirm the report commit and push from
the final handoff or `git ls-remote origin refs/heads/main`.
