# Kafka fraud transport and feature worker (Phase 02 / Checkpoint 03)

Kafka transports typed fraud facts and retains the replay history for derived Redis state. It is not transactional decision or audit authority; PostgreSQL retains that role. The worker does not serve HTTP and contains no feature calculations.

## Topic and wire contract

`argus.fraud-events.v1` has three partitions, local replication factor 1,
`retention.ms=-1`, `retention.bytes=-1`, and delete cleanup policy. RF=1 is for
the one-broker development cluster, not a production recommendation.
`kafka-init` explicitly creates or verifies the topic and rejects incompatible
partition, replication, or retention settings. Broker auto-topic creation is
disabled. Infinite retention supports exact replay of the current unbounded
features, especially `accounts_on_device`; unbounded Kafka disk use is accepted
Phase-2 debt.

Records contain deterministic UTF-8 JSON for the validated version-one fraud envelope. Deserialization chooses the concrete payload from `(event_type, event_version)` and validates the complete contract. The Kafka key is UTF-8 `payload.user_id` for all five events. `subject_id` keeps its separate envelope meaning: for `payment.attempted`, it is `payment_id`, while the Kafka key is `user_id`. Events for one user enter one partition, but feature correctness does not depend on delivery order. Cross-user device observations may arrive from different partitions; Redis's atomic earliest-observation update converges them by event time.

The producer uses Confluent's synchronous delivery acknowledgement, `enable.idempotence=true`, and `acks=all`. The caller supplies the complete event, including `event_id`, `occurred_at`, and `trace_id`, and reuses that identity on publish retries. Producer idempotence is not logical event idempotency. Distinct records or producers may publish the same fact, so Redis deduplicates by `event_id`.

## Live processing and failure

The live group is `argus-feature-projection-v1` by default. It uses the client
and broker rebalance defaults (the local broker observed a classic group; no
explicit protocol or session tuning), `enable.auto.commit=false`,
`enable.auto.offset.store=false`, and `auto.offset.reset=earliest`. A successful
`APPLIED` or `DUPLICATE` Redis result permits a synchronous commit of
`message.offset + 1`. Returned per-partition commit errors are checked. One
message per commit favors visible correctness over throughput. A group restart
resumes after its committed offsets; a fresh group begins at earliest.

Delivery is **at least once**. If Redis applied an event and the worker crashes before commit, Kafka redelivers it. Redis returns `DUPLICATE`, then the worker commits. If Redis reports a connection, timeout, OOM, or script error, its mutation outcome is unknown; the worker does not commit. Redelivery reconciles either a complete prior write (`DUPLICATE`) or an incomplete write: payment/failure sorted-set members are event IDs, device members are user IDs with only-earlier scores, and event identity is recorded for completed scripts. A commit failure after Redis application also leaves the event for safe redelivery. No Redis undo occurs.

Invalid JSON, unsupported contracts, wrong record keys, identity conflicts, and Kafka errors fail the worker without committing the offending record. A poison record may block its partition. There is no DLQ, skip policy, retry counter, or aggressive restart loop in this checkpoint. Failure policy is deferred.

## Rebuild and lifecycle

At startup, `UNINITIALIZED` begins a rebuild; `REBUILDING` resumes it from the Kafka beginning; `READY` enters live consumption. Rebuild uses a separate consumer with manual assignment of every partition at its low offset. It requires low offset zero for exact full-history replay and captures each partition's high watermark as a fixed cutoff. It applies every offset below each cutoff, then marks Redis `READY`. Empty history is valid. It never commits live group offsets or derives replay positions from them.

A crash leaves Redis `REBUILDING`; replaying from zero again is safe. Events published after a captured cutoff are processed by the live group after readiness. There is no globally atomic Kafka/Redis handoff, so normal consumer lag and a harmless first-start duplicate pass are possible. If history has been truncated, rebuild fails explicitly rather than claiming exact state.

## Current dependencies

```text
Decision API -> PostgreSQL
Feature Worker -> Kafka, Redis
Investigator API -> none
```
