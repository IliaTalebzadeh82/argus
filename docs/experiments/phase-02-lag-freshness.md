# Phase 02 / Checkpoint 05: lag and freshness campaign

## Environment

Local development Compose stack, Kafka `4.3.1`, Redis `7.2.16`, PostgreSQL `17.11`; three partitions, one broker, live worker group `argus-feature-projection-v1`. The real Kafka/Redis/PostgreSQL tests used host URLs and a FastAPI `TestClient` against migrated PostgreSQL. The stale case used the **default topic and live group** with an isolated Redis namespace and explicitly stopped in-process consumer. Other failure tests used three-partition isolated topics/groups. No production throughput or latency claim follows from this laptop run.

## Baseline

With the controlled worker caught up, Kafka lag was **0** and Redis lifecycle was `READY`. Decision readiness returned **200**. One unique user/device had `payments_10m=0`, `failed_payments_1h=0`, and `accounts_on_device=1`; a fresh-key decision returned **ALLOW**. The lag probe also found a live-topic partition with `committed_offset=null`, low/high both 0, correctly distinct from a committed zero offset.

## Known Kafka backlog

The consumer closed while Kafka, Redis, and PostgreSQL remained available. Thirty unique `payment.attempted` events inside the decision's event-time window were acknowledged on the default topic. The live group diagnostic reported **30 pending records**. Redis remained `READY`: its snapshot for the user at `T` had `payments_10m=0`; CP01 `ReferenceFeatureProjector` over all 30 logical events had `payments_10m=30`. Other features remained `failed_payments_1h=0`, `accounts_on_device=1`. Readiness still returned **200**. A fresh-key decision at `T` returned **ALLOW** from the valid but behind Redis snapshot; reference count 30 crosses the deployed threshold 5 and would yield CHALLENGE. Redis was not corrupted.

## Catch-up

Restarting controlled consumption drained **30 to 0** pending records in **4.515 seconds** measured with `time.monotonic()` in the final default-topic run. Redis then matched reference at `payments_10m=30`, and a new-key decision returned **CHALLENGE**. Replaying the original lagging request with its original key returned the same historical **ALLOW**, `replayed=true`, and identical decision ID/content. PostgreSQL is historical decision authority; Redis supplies current derived features. The worker synchronously commits each message, so each record incurs a commit round trip. This run is not a benchmark or SLO. A separate isolated lag test observed 6 pending records and zero after commit.

## Late event at zero lag

With the live group at **zero lag**, a fresh user at `T` had `payments_10m=0` and an **ALLOW** decision. Afterwards, five new payment records arrived with `occurred_at=T-1 second`, though broker arrival was after the decision. After full consumption, lag returned to **zero**; Redis and reference at the same historical `T` both showed `payments_10m=5`. A new-key request with identical facts returned **CHALLENGE**. Zero lag certifies only processing through records currently at broker high watermarks. It cannot rule out future arrival of earlier event-time facts.

## Consumer rebalance

On an isolated three-partition topic, Admin group inspection observed **2 members**, with disjoint assignments **[0,1] / [2]** in this run. Assignment is not fixed by contract. Initial lag was **16**. Both workers committed a record. One then applied another record to Redis without committing and closed. Inspection observed **1 member** with **[0,1,2]**; lag drained to **0**. All 16 delivered records were processed, including a rebalance redelivery, and final Redis snapshots matched CP01 reference. Five `DUPLICATE` apply results were observed: four explicit repeated logical records and one applied-before-rebalance redelivery. The test waits on group state and finite monotonic deadlines.

## Poison record

On an isolated group, valid A, malformed P, and valid B were published with the same key into partition **0** at offsets **0,1,2**. A applied and committed next offset **1**. P raised an invalid-record error and remained uncommitted; after consumer close/restart, P at offset **1** was delivered again. Lag remained **2** (P and B), and Redis contained only A's single payment contribution. B could not advance behind P under this fail-stop processing. Kafka ordering is partition-local; a different partition's already committed records remain valid. The current single-threaded worker process exits on the unhandled poison exception, so its practical availability impact can extend beyond that partition. No skip, DLQ, or recovery policy was added.

## Duplicate and out-of-order

The rebalance test published **16 Kafka records for 12 logical events** with deliberate repeated IDs and differing delivery/event-time order. Five duplicate results included the extra rebalance redelivery. For all users, Redis equaled CP01 reference both at `T` and a historical `T-2 minutes`. Event-time sorting in the worker was unnecessary for convergence.

## Current-payment race

The late-event test directly demonstrates that a decision can complete before related payment events become visible in Redis. More specifically, the HTTP request's `payment_attempt` and Kafka's `payment.attempted` are separate flows with no shared ingestion barrier or event identity contract. If the request precedes its corresponding event's projection, `payments_10m` excludes that attempt. If the event was already projected, it includes it. Request-time `+1` would risk double counting and is not implemented.

## Conclusions

- `READY` guarantees an existing queryable projection whose rebuild completed to its captured cutoff. It does not continuously certify zero live backlog.
- Lag zero means the group committed through broker high watermarks observed by the diagnostic, subject to non-atomic measurement and immediate subsequent arrivals. It is transport catch-up, not event-time completeness.
- Neither state guarantees all facts with `occurred_at <= T` have arrived, nor that a request's own payment event is projected. PostgreSQL preserves decisions made with the evidence then visible.

## Recommendation

Keep current behavior pending an explicit freshness objective and more measurements. The options are: **A**, current READY-based decisions, favoring availability/latency while accepting behind projections; **B**, gate on zero Kafka lag, avoiding known backlog but coupling API availability to Kafka/control-plane queries, rejecting during transient lag, leaving a measurement race, and still allowing late events; **C**, request-specific processing barrier/token, offering read-after-ingestion for a referenced position at the cost of new request/event correlation and latency; **D**, bounded eventual consistency with a later measured freshness SLO and lag metrics rather than hard gating. Evidence supports designing a request/event correlation contract before considering C. Event-time completeness would separately require upstream guarantees, watermarks, or allowed-lateness policy. No option is implemented here.
