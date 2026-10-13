# Codex Checkpoint Protocol

This file defines how Codex work is divided, persisted, reviewed, and handed back to ChatGPT.

## 1. Unit of work

The unit of execution is a **checkpoint**, not a whole multi-week phase.

A checkpoint must:
1. have one clear engineering objective;
2. have explicit in-scope and out-of-scope items;
3. have measurable acceptance criteria;
4. end in a stable repository state;
5. produce a report;
6. commit and push its work.

A phase may contain several checkpoints. The final checkpoint of a phase additionally creates the phase review required by `ARGUS_MASTER_REFERENCE.md`.

## 2. Context policy

Start a **fresh Codex thread for every checkpoint**.

Repository files are the durable memory. Codex chat history is disposable.

For each checkpoint, read:
- `AGENTS.md`;
- the checkpoint prompt;
- only the relevant sections of `ARGUS_MASTER_REFERENCE.md`;
- directly relevant code, ADRs, and the previous checkpoint report.

Do not reread the full master reference by default.

This is intentional: it reduces context accumulation, compaction, repeated tokens, and stale conversational assumptions.

## 3. Scope discipline

Codex must not:
- implement later checkpoints;
- perform broad refactors not required by acceptance criteria;
- introduce speculative infrastructure;
- change an accepted architectural invariant silently;
- substitute a different technology merely because it is familiar.

If a material change is justified, create an ADR and call it out in the report.

## 4. Validation budget

Use the narrowest validation that proves the checkpoint:
1. targeted unit/static checks while iterating;
2. affected integration checks;
3. one checkpoint-level validation pass.

Do not repeatedly run the entire suite after every small edit.

For the final checkpoint of a phase, run the complete phase-relevant suite.

## 5. Git protocol

Before implementation:
- inspect `git status`, current branch, and remote;
- do not destroy unrelated user work.

At checkpoint completion:
1. ensure tests/validation pass;
2. ensure no secrets or local artifacts are staged;
3. create implementation commit:
   `phase-XX/cp-YY: <imperative summary>`
4. capture implementation SHA;
5. create `docs/codex/reports/phase-XX-cp-YY.md`;
6. commit the report:
   `docs: checkpoint phase-XX cp-YY report`
7. push current branch to `origin`;
8. verify push succeeded;
9. leave worktree clean.

For an emergency context checkpoint, use:
`phase-XX/cp-YY-partial: <stable partial state>`

Never claim a push succeeded without command confirmation.

## 6. Emergency context checkpoint

Use only when the active session is becoming too context-heavy or compaction makes continued execution risky.

Before stopping:
- finish the smallest coherent unit currently in progress;
- run the relevant test(s);
- commit safe partial work;
- write a report named:
  `docs/codex/reports/phase-XX-cp-YY-context-N.md`
- include exact remaining work;
- push if possible;
- stop.

The next Codex thread resumes from the report and repository, not from old chat history.

## 7. Dependency and infrastructure rule

Adding any new dependency must answer:
- what concrete checkpoint requirement needs it?
- why standard library/current stack is insufficient?
- what operational cost does it add?

Major infrastructure changes require an ADR under `docs/adr/`.

## 8. Usage-efficiency rule

Prefer:
- existing repository context over repeated prose in prompts;
- focused file reads over whole-repo scans;
- targeted tests during iteration;
- one agent unless parallelism clearly reduces total work;
- medium reasoning for implementation;
- higher reasoning only for consequential architecture/debugging decisions.

Do not use subagents merely to review work the main agent can validate directly.

## 9. Handoff

The user will paste Codex's final checkpoint report into ChatGPT.

ChatGPT will:
- review correctness and scope;
- identify gaps or architectural concerns;
- decide whether the checkpoint passes;
- produce the next checkpoint prompt.

Codex must therefore make the final report sufficient for review without requiring the prior Codex conversation.
