# Phase 02 review — event-driven online features

## Status

**PASS.** The original duplicate gate and the broader event-driven feature contract are demonstrated by pure tests and real Kafka/Redis/PostgreSQL experiments. The current freshness guarantee is deliberately eventual; it does not claim synchronous or complete event-time reads. The Phase 2 behavior has no known correctness defect against that contract.

## 1. What was built?

CP01 defined five typed version-one fraud facts and a pure reference projector as the semantic oracle. CP02 implemented the same three online features in an atomic Redis projection with explicit lifecycle. CP03 added a three-partition Kafka topic, at-least-once worker, post-apply offset commits, and full-history Redis rebuild. CP04 connected new facts-only Decision API requests to Redis snapshots and persisted the exact resulting signals in PostgreSQL. CP05 measured Kafka lag, stale decisions, late facts, rebalances, duplicates, and poison behavior. The resulting path is typed facts → Kafka → feature worker → derived Redis → deterministic Decision API → authoritative PostgreSQL decision/audit history. The Investigator API remains liveness-only.

## 2. What changed from the master plan?

No material architectural deviation. The pure reference projector, Redis `UNINITIALIZED`/`REBUILDING`/`READY` lifecycle, and full Kafka replay make the planned feature pipeline testable and recoverable. Infinite local Kafka retention supports exact current replay, with disk growth explicitly deferred. Facts-only Decision API input assigns online feature ownership to Redis. The Kafka lag probe is operator-only observability. These elaborate the planned at-least-once, derived-state design rather than changing its authorities or guarantees.

## 3. Why did it change?

No material architectural deviation. The elaborations were needed to define an exact semantic oracle, fail visibly on missing Redis state, rebuild without depending on live offsets, and keep fraud evidence attributable. No freshness strategy was selected.

## 4. What failed?

**Design and correctness discoveries:** `READY` can be stale relative to available Kafka records. Zero lag proves only progress to observed broker high watermarks, not event-time completeness. A decision request and its `payment.attempted` event have no processing barrier, so the API cannot establish whether its own attempt is already counted. Invalid poison records fail the worker without an offset commit and can block a partition indefinitely. These are explicit current limitations, not hidden Phase 2 guarantees.

**Implementation and tooling:** CP03 corrected a Confluent Admin API shape mistake and observed coordinator startup timing after a Kafka restart. CP05 corrected a Confluent import, an Admin-client lifetime mistake, and a rebalance test that discarded a polled record. CP01/CP02 fixed lint/format issues; CP04 fixed a missing test Redis URL. Each affected check was rerun successfully. The upstream Starlette/AnyIO deprecation warning is separate.

## 5. What was learned?

- `event_id` names one logical fact; a Kafka delivery is an attempt to transport it. Multiple deliveries do not create multiple business activities. An identical full event under the same ID returns `DUPLICATE`; changed metadata or payload under that ID is an identity conflict. `produced_at` participates in identity comparison.
- `occurred_at` is when the fact happened, `produced_at` when the integration event was emitted, and processing time when the worker handled it. Features use `occurred_at`. `payments_10m` counts unique attempts in `(as_of - 10 minutes, as_of]`; `failed_payments_1h` counts unique failures in `(as_of - 1 hour, as_of]`; `accounts_on_device` counts distinct users observed on the device at or before `as_of`. A missing device is unknown, not known zero. The CP01 pure projector is the I/O-free semantic correctness oracle, not production storage.
- Redis is derived. Loss means `UNINITIALIZED`, not zero features. Explicit rebuild moves it to `REBUILDING`, where queries fail, then `READY` after a captured Kafka-history cutoff has been applied. Redis Lua serializes event registration and feature mutation and reads a whole snapshot atomically. A Redis operational error can leave completion unknown because a script's earlier writes are not rolled back; reapplying the same ID reconciles complete or partial effects.
- The worker commits only after Redis returns `APPLIED` or `DUPLICATE`. Committing before Redis would permanently skip an unapplied record. A committed offset is the **next** position, so pending lag is `high watermark - committed offset`, with no extra subtraction. Kafka can redeliver after a crash, failed commit, or rebalance. This is **at-least-once delivery plus idempotent Redis side effects**, not exactly-once execution.
- One Kafka partition belongs to one active group member at a time; ownership changes on rebalance. A fresh Redis rebuild manually reads retained history from offset zero through captured high offsets and ignores the live group's committed positions. Otherwise an empty Redis would inherit the group's latest position and omit earlier facts. The Kafka key is `payload.user_id` for per-user locality; envelope `subject_id` names the fact's primary entity and is often different. Device observations from users on separate partitions converge through Redis's earliest event-time observation per device/user.
- `READY` means the Redis projection is initialized and queryable after its last rebuild cutoff; it does **not** mean the live group is caught up. In CP05, 30 broker records were pending, Redis/reference `payments_10m` were **0/30**, API readiness was **200**, and a new decision was **ALLOW**. After catch-up, Redis was **30** and a new-key decision was **CHALLENGE**. The original key still replayed its historical **ALLOW**. PostgreSQL stores the exact `redis_features_v1` signals used at commitment; later Redis state never rewrites that judgment.
- Zero lag is not an event-time watermark. CP05 observed lag **0**, payments **0**, and **ALLOW** at `T`; then five records arrived with `occurred_at < T`. After consumption lag was again **0**, payments at `T` were **5**, and a new-key decision was **CHALLENGE**. Broker progress cannot certify that future late facts will not arrive. The independent HTTP request and Kafka payment event also prevent the API from knowing if that attempt is included; blindly adding one risks double counting.
- A malformed Kafka record fails before offset commit. On restart it redelivers, and later records in that partition cannot progress under the current fail-stop worker. There is no skip/DLQ policy yet.

## 6. What metrics were observed?

CP06 offline validation: **176 passed**, one upstream warning. Earlier real integrations: CP02 **7 Redis tests**, CP03 **11 Kafka/Redis tests**, CP05 **4 failure-campaign tests**. Local Kafka **4.3.1**, Redis **7.2.16**, topic **3 partitions**. CP05 measured **30** pending records, Redis/reference **0/30**, then a **4.515-second** local catch-up and **ALLOW → CHALLENGE** for new decisions. Late facts changed payments **0 → 5**. Two workers owned partitions **[0,1] / [2]**, then one owned **[0,1,2]**. There were **16 deliveries for 12 logical events** and **5 `DUPLICATE` results**, including redelivery around rebalance. The local catch-up timing is neither a production benchmark nor an SLO.

## 7. What technical debt was introduced?

**Deliberately deferred design:** bounded Kafka retention, bounded Redis retention, dedup TTL, watermarks, allowed lateness, a freshness SLO, a request/event processing barrier, poison recovery or DLQ, and batched offset commits. Their interaction needs a future explicit contract; arbitrary TTL or retention could break replay or late-event semantics.

**Local development limits:** one Kafka broker, replication factor 1, and unbounded local Kafka history. Redis history and dedup state are also intentionally unbounded. The held PostgreSQL transaction during the Redis read and per-record synchronous commits are known throughput costs to measure under future load; they are not Phase 2 correctness compromises. No other known undesirable correctness debt remains. The Starlette/AnyIO warning is an upstream dependency warning.

## 8. Is Phase 3 still correct?

Yes. Phase 2 met its intended duplicate and replay gate. Stronger freshness needs a specified product guarantee and availability trade-off. Phase 3's deterministic synthetic world and load generator can reveal realistic arrival, lateness, and lag distributions before choosing an SLO or barrier. There is no evidence requiring another mandatory implementation phase first. Phase 3 remains unstarted here.

## 9. Does the master plan need an ADR/update?

No ADR is warranted: at-least-once plus idempotent effects, derived Redis lifecycle, full Kafka replay, infinite Phase-2 local retention, facts-only feature ownership, and the READY/lag/event-time distinction elaborate the existing master plan. No freshness strategy was selected, so an ADR choosing one would be premature. This review records the precise Phase-2 contract; no master-reference change is needed.

## Freshness Guarantee Decision

Phase 2 provides **eventually consistent online features**. A decision may use a Redis projection that is `READY` yet behind currently available Kafka records. Kafka lag is observable to operators but is not part of the decision availability contract or fraud evidence. Argus does not guarantee read-after-ingestion for a payment decision or event-time completeness for its `as_of`. Historical decisions preserve the exact feature evidence visible when the judgment was committed.

| Future option | Guarantee gained | Cost and remaining limit |
| --- | --- | --- |
| A. Current `READY` decisions | Initialized, queryable projection | May be behind Kafka. |
| B. Require lag zero | Avoids a backlog known at the measurement instant | Adds Kafka/control-plane dependency, transient-lag sensitivity, lower availability, and a measurement race; still cannot prove late-event completeness. |
| C. Request-specific processing barrier/token | Stronger read-after-ingestion for a referenced event/position | Requires request/event correlation, latency, and protocol complexity; cannot rule out arbitrary future late facts. |
| D. Bounded eventual consistency plus freshness SLO | Measurable operational objective instead of hard synchrony | Needs metrics, thresholds, and operational policy; event-time completeness still needs a lateness contract. |

**Preliminary recommendation:** retain Kafka lag as observability and keep the current availability contract for now. Define product freshness requirements and measure realistic traffic before selecting a stronger guarantee. If read-after-ingestion is required, design explicit request/event correlation and a processing barrier. Treat late-event completeness as a separate problem.

## Duplicate and crash gates

The original duplicate gate has direct measured evidence. CP02's real Redis concurrency test applied the same logical event twice: one `APPLIED`, one `DUPLICATE`, and exactly one contribution, equal to the CP01 reference. CP03's real Kafka/Redis live-history test observed **6 `APPLIED` and 1 `DUPLICATE`** result with Redis/reference snapshot equality. CP05's rebalance campaign saw **16 Kafka deliveries of 12 logical events**, including repeated `event_id` values, and **5 `DUPLICATE`** results; final Redis/reference snapshots matched. Thus repeat transport delivery did not increase a logical event's feature contribution beyond once.

CP03 also exercised real apply-before-commit redelivery: Kafka delivered E, Redis returned `APPLIED`, the consumer stopped before committing, Kafka redelivered E to the group, Redis returned `DUPLICATE`, and the worker committed `offset+1`. A separate unknown-Redis-response case converged the same way. These prove idempotent effects around at-least-once processing, not exactly-once execution. CP02 proved Redis loss and local deterministic replay. CP03 then proved actual Redis loss → `UNINITIALIZED` → full-history Kafka replay → `READY`, with rebuilt snapshots matching the CP01 reference. The live group's committed offsets were intentionally not used for rebuild.

## Phase 2 Gate

1. **One logical event:** one producer-assigned `event_id` for one validated domain fact.
2. **Repeated Kafka delivery:** uncommitted work can redeliver after restart, failure, or rebalance; the producer can also retry.
3. **No double count:** Redis compares canonical event identity and applies each ID once; identical replay returns `DUPLICATE`.
4. **Not exactly once:** transport and worker execution may repeat; only the feature side effect is idempotent.
5. **Crash after apply:** the offset remains uncommitted, Kafka redelivers, Redis returns `DUPLICATE`, then the next offset is committed. CP03 proved this with real Kafka/Redis.
6. **Commit `offset+1`:** Kafka stores the next record position; committing the current position would request it again.
7. **Use `occurred_at`:** windows represent when facts happened, independent of publication or worker delay.
8. **Older event later:** delayed production, retries, skew, backfill, and different partitions can deliver older event times after newer ones.
9. **Redis convergence:** sorted-set event-time scores, event-ID deduplication, and earliest device/user observations make arrival order irrelevant within retained history.
10. **Delete Redis, not PostgreSQL:** Redis is a replayable projection; PostgreSQL holds authoritative decisions and audit records that Kafka feature history cannot recreate.
11. **Kafka rebuild:** manually replay every retained partition from offset zero to a captured high cutoff, independent of live group commits, then mark `READY`.
12. **`READY`:** the projection completed its rebuild cutoff and can answer queries; the live group may still lag.
13. **Lag zero:** at observation, the next committed position matched each broker partition's current high watermark.
14. **No completeness from lag zero:** future records may carry `occurred_at` before the query time.
15. **ALLOW with 30 pending:** Redis was `READY` but had not yet projected those 30 Kafka records, so its valid snapshot contained zero payments.
16. **Original ALLOW persists:** its idempotency key returns the committed PostgreSQL decision and exact recorded signals without recomputing Redis.
17. **Poison now:** validation fails, no commit occurs, restart redelivers it, and later same-partition records remain blocked.
18. **No blind current-attempt increment:** the HTTP request and Kafka event are independent; the attempt may already be projected, so adding one could count it twice.

## Architecture invariants

All reviewed invariants hold: [x] `event_id` is logical identity; [x] type/version/payload/subject coherence is validated; [x] windows use `occurred_at`; [x] exact duplicates contribute once; [x] same-ID conflicts fail; [x] out-of-order delivery converges; [x] Redis is derived and rebuildable; [x] Redis loss cannot silently become zero; [x] `READY` is not described as zero lag; [x] Kafka processing is at least once; [x] offsets commit only after `APPLIED`/`DUPLICATE`; [x] crash-before-commit redelivery is safe; [x] rebuild ignores live committed offsets; [x] current Kafka retention preserves complete Phase-2 history; [x] Decision API has no Kafka dependency and reads Redis online evidence; [x] PostgreSQL persists exact signals; [x] historical idempotent replay does not recompute them; [x] lag is operational metadata, not fraud evidence; [x] no event-time completeness is claimed; [x] PostgreSQL is decision/audit authority; [x] Redis is non-authoritative; [x] Phase 2 has no ML or LLM decision component.

Scope review: no DLQ, watermark, allowed-lateness implementation, Kafka-lag readiness gate, request-processing barrier, Kafka client in Decision API, ML, or LLM was introduced.
