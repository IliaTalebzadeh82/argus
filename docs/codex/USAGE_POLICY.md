# Codex Usage Policy for Argus

The goal is to minimize Codex usage without sacrificing correctness.

## Default execution profile

- Fresh thread per checkpoint.
- Default reasoning: medium.
- Plan-mode reasoning: high.
- Multi-agent: disabled by default.
- Workspace-write sandbox.
- Network allowed.
- Approval policy: on-request, with auto-review when available.

## Raise reasoning to high when

Use high reasoning for a checkpoint when it includes:
- data consistency or transaction-boundary design;
- event ordering/idempotency semantics;
- schema migration strategy with meaningful compatibility risk;
- concurrency bugs;
- ML leakage/temporal correctness;
- LLM security/trust boundaries;
- architectural ADRs with difficult trade-offs.

Return to medium afterward.

## Consider multi-agent only when

Parallel work is truly independent, for example:
- one agent performs a read-only architecture/security review while another executes an already-decided implementation;
- independent load-test analysis and documentation can happen concurrently.

Do not use multi-agent for ordinary feature implementation.

## Avoid

- full repository scans without need;
- rereading the entire master reference every checkpoint;
- repeated full-suite tests during iterative edits;
- asking subagents to restate the same context;
- speculative refactors;
- generating long planning documents when acceptance criteria are already clear.

## Context checkpoints

Fixed checkpoints are preferred over waiting for the context window to become stressed.

If a checkpoint grows unexpectedly, create an emergency context checkpoint rather than continuing after compaction with weakened context.
