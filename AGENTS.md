# AGENTS.md — Argus

Argus is governed by `ARGUS_MASTER_REFERENCE.md`. Use it as the architectural source of truth, but read only the sections relevant to the current checkpoint unless the task genuinely spans the document.

## Working contract

- Work only on the checkpoint explicitly requested by the user. Do not implement later phases opportunistically.
- Preserve the core boundary: deterministic rules/predictive ML may enter the critical decision path; generative AI must not be required for critical-path availability or correctness.
- PostgreSQL is authoritative transactional/audit state unless an accepted ADR says otherwise. Redis and later semantic/analytical stores are derived state.
- Assume at-least-once event delivery; do not design consumers around exactly-once assumptions.
- Do not add infrastructure, frameworks, databases, or abstractions without a concrete need from the active checkpoint or an accepted ADR.
- Prefer the simplest implementation that preserves explicit guarantees and can evolve in later phases.
- Do not hide core learning objectives behind a framework when the master reference says to learn the primitive first.

## Checkpoint execution

Follow `docs/codex/CHECKPOINT_PROTOCOL.md`.

Within a checkpoint:
- inspect only the code/docs needed to complete the scope;
- implement to the checkpoint acceptance criteria;
- run relevant tests and validation, fix failures caused by the work, and rerun affected checks;
- do not spend context on unrelated cleanup;
- record material architectural deviations in an ADR;
- stop at the checkpoint boundary even if later work looks easy.

Local tests and project containers are disposable development resources with no production access. You may run, restart, rebuild, and inspect them as needed for the requested checkpoint.

## Git

At a successful checkpoint:
- leave the worktree clean;
- create an implementation commit using `phase-XX/cp-YY: <summary>`;
- create/update the checkpoint report after the implementation commit, referencing that implementation SHA;
- commit the report using `docs: checkpoint phase-XX cp-YY report`;
- push the current branch to `origin`;
- never rewrite published history unless the user explicitly asks.

If pushing is blocked by authentication, permissions, network policy, or missing remote setup, do not fake success. Preserve the completed local commits and report the exact blocker.

## Reporting

The final response for every checkpoint must follow the report contract in `docs/codex/REPORT_TEMPLATE.md`. Be concise but include exact commands/results needed for independent review.

If the session becomes context-constrained before the checkpoint is complete, first get the repository into a coherent, testable state, commit the safe partial work, write an **emergency context checkpoint** report, push if possible, and stop. Do not continue into a degraded long-context session.
