# Phase 02 / Checkpoint 01 — feature pipeline semantics

## Logical events and delivery

`event_id` identifies a logical fact; delivery count is not event count. A producer supplies the UUID and preserves it across retries. The pure reference projector accepts the five version-one fraud contracts through `validate_fraud_event`, which checks the envelope's type, version, payload class, and primary subject. Payloads hold event-specific facts and omit envelope metadata. IDs inside payloads are opaque, non-empty strings. No event depends on another event arriving first.

| Contract | Required payload IDs | `subject_id` |
| --- | --- | --- |
| `account.created` | `user_id`; optional `device_id` | `user_id` |
| `payment.attempted` | `payment_id`, `transaction_id`, `user_id` | `payment_id` |
| `payment.failed` | `payment_id`, `transaction_id`, `user_id` | `payment_id` |
| `transaction.completed` | `transaction_id`, `user_id` | `transaction_id` |
| `chargeback.received` | `chargeback_id`, `transaction_id`, `user_id` | `chargeback_id` |

A missing `device_id` in `account.created` means this fact supplies no device observation. A device can appear with several users and a user can appear with several devices; this contract makes no ownership claim. `subject_id` is the primary entity identity, not a Kafka partition key.

## Event time and features

`occurred_at` is the feature time. `produced_at` records integration publication time. Processing or arrival time has no role in pure feature truth. Query `as_of` is explicit, aware, and normalized to UTC; no clock is read.

| Feature | Semantics at `as_of` |
| --- | --- |
| `payments_10m` | Count unique logical `payment.attempted` events for the queried user in `(as_of - 10 minutes, as_of]`. |
| `failed_payments_1h` | Count unique logical `payment.failed` events for the queried user in `(as_of - 1 hour, as_of]`. |
| `accounts_on_device` | Count distinct `user_id` values in `account.created` facts for the specified device with `occurred_at <= as_of`. No rolling window. |

The exact lower window endpoint is excluded and the upper endpoint included. Future events do not contribute to earlier snapshots. If no device is supplied, `accounts_on_device` is `None`: absent device evidence is not known zero. If a device is supplied and has no matching facts, the count is zero. The device count is a demonstration feature definition, not a universal fraud definition. `transaction.completed` and `chargeback.received` are valid facts but do not alter these three features.

## Duplicates, order, and replay

The first delivery of an event ID returns `APPLIED`. An identical redelivery returns `DUPLICATE` and changes no state. Reusing the same ID with different recorded metadata or payload raises `EventIdentityConflict`, because one identity cannot name two facts. The comparison includes `produced_at`, although production time never moves an event between feature windows.

The projector retains full validated logical event history and calculates temporal views from `occurred_at`. Unique facts delivered in any order produce the same result. A fresh projector replaying the same history, including repeated deliveries, rebuilds equal snapshots. It has no I/O, wall clock, broker offsets, or background work. **This in-memory projector is a correctness reference, not the production online store.** It may retain more state than a later Redis projection.

## Deferred distributed decisions

The Redis projection key schema, atomic operations, and lifecycle are documented in [redis-feature-projection.md](redis-feature-projection.md). Kafka topic design, partition keys, consumer groups, offset commits, dedup TTL, watermarks, late-event policy, DLQ, and retry policy remain deferred. The reference accepts valid out-of-order events without a lateness cutoff. No Decision API integration is part of this checkpoint.
