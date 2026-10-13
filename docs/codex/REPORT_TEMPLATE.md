# Codex Checkpoint Report Template

Use this exact section structure in both the saved report and final response.

# Phase XX / Checkpoint YY — <name>

## Status
`PASS` | `PARTIAL` | `BLOCKED`

## Objective
One short paragraph.

## Implemented
Concise bullets of what changed.

## Key decisions
Only decisions that matter to architecture, correctness, future phases, or learning.

## Files changed
Group by purpose. Do not dump every generated/cache file.

## Validation
For each relevant command:
- command;
- result;
- important counts/observations.

Include failures encountered and how they were resolved.

## Acceptance criteria
- [x] ...
- [ ] ...

## Architecture / invariants check
State whether this checkpoint:
- preserved the master reference;
- created any ADR;
- introduced any deliberate deviation.

## Git
- Branch:
- Implementation commit:
- Report commit:
- Remote:
- Push result:
- Final `git status`:

## Resource / usage notes
Report measured values only when available. Do not estimate token counts.
Mention unusually expensive scans/tests/builds and how future checkpoints can avoid repeating them.

## Risks / technical debt
Only concrete remaining concerns.

## Next recommended checkpoint
One paragraph. Do not implement it.

## Handoff notes for ChatGPT
Anything ChatGPT must know to review this checkpoint independently.
