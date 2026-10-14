# Redis derived feature projection (Phase 02 / Checkpoint 02)

## Authority and dependency graph

Redis holds rebuildable online feature state, not transactional, audit, or event authority. PostgreSQL remains authoritative for Phase-1 decisions. Current dependencies are:

```text
Redis projection capability -> Redis
Decision API -> PostgreSQL
Investigator API -> none
```

No feature worker is running yet. The caller explicitly supplies the Redis URL and invokes `begin_rebuild`, `apply`, `mark_ready`, and `features_for`. There is no Decision API Redis connection.

## Keys and exact event time

The default namespace is `argus:features:v1:`; callers may provide a unique prefix for isolated tests. Opaque user and device IDs are UTF-8 encoded and hexed in key names, so punctuation and Unicode cannot collide with separators. Structures are:

| Key | Redis type | Content |
| --- | --- | --- |
| `state` | string | `REBUILDING` or `READY` |
| `events` | hash | UUID -> canonical, sorted-key JSON of the complete validated event |
| `payments:<user hex>` | sorted set | event UUID -> occurrence time |
| `failures:<user hex>` | sorted set | event UUID -> occurrence time |
| `device:<device hex>` | sorted set | user ID -> earliest `account.created` occurrence time |

Scores are integer microseconds since the Unix epoch. The Python boundary rejects timestamps outside `[-2^53, 2^53]` microseconds, where Redis double scores preserve every integer. Query window starts are checked too. `(as_of - 10m, as_of]` and `(as_of - 1h, as_of]` use exclusive lower and inclusive upper score bounds. Device queries count users with earliest observation at or before `as_of`; an earlier event delivered later updates that score. `produced_at` is part of identity, never feature time.

## Atomic operations and lifecycle

One Redis Lua operation checks lifecycle and event ID, applies its feature mutation, and records the canonical identity. Repeating the identical event returns `DUPLICATE`; reusing the ID with changed event data raises `EventIdentityConflict`. Events without current feature effects still register identity. Redis serializes scripts, so concurrent duplicate delivery contributes once. Every key used by each script is passed through `KEYS`.

One Lua read checks readiness and counts all three features at one Redis execution point. This prevents a snapshot assembled from different concurrent moments. `as_of` is caller supplied; neither script reads a clock.

Absent state is `UNINITIALIZED`: applying or querying fails. Only explicit `begin_rebuild` transitions absent state to `REBUILDING`; events may be applied then, but queries fail. `mark_ready` transitions `REBUILDING` to `READY`, after which queries and live application are allowed. Invalid transitions fail, including an in-place `READY` to `REBUILDING` transition. There is no automatic initialization.

## Failure and retention

Redis snapshots and AOF remain disabled. After actual Redis memory loss, the state key disappears and queries fail as uninitialized until deterministic history is replayed and marked ready. Connection, out-of-memory, and script failures surface as Redis errors; they are not converted to success or zero features. A caller receiving a write error must treat completion as unknown and reconcile or redeliver the same event ID. Lua serializes execution but Redis does not roll back earlier script commands on a runtime error. Feature mutations use event IDs as sorted-set members, and device scores only move earlier, so identical redelivery is safe if a write fails before identity registration. Operational recovery and future replay policy remain separate work.

Local Redis uses `noeviction` with the existing 384 MiB key-memory limit: **explicit write failure is preferable to silent feature-key eviction**. No feature, identity, or dedup key has a TTL. This intentionally unbounded state has no watermark, lateness cutoff, or retention policy in CP02; bounded retention requires a later explicit design.
