# Legitimate synthetic world (Phase 03 / Checkpoint 02)

## Purpose and population

This pure scenario provides baseline non-fraud behavior for future comparisons.
Each user has exactly one unique legitimate device. Merchant IDs form an ordered
pool from `merchant-000001` through `merchant-{merchant_count:06d}`. Production
`UserAccount`, `Device`, `Money`, `Transaction`, and `PaymentAttempt` snapshots
represent the world; no parallel simulation domain model is needed.

## Payments and random-stream ownership

Every planned payment creates one transaction and one payment attempt. Its
amount is an integer number of currency minor units in the configured inclusive
range. A dedicated per-user stream owns each independent draw dimension:
`payments:{user_id}:amount`, `payments:{user_id}:merchant`, and
`payments:{user_id}:outcome`. A failure is ordinary payment noise, not fraud.
Adding users after existing users cannot shift their random behavior. The
merchant pool is an ordered tuple, so selection has a stable input order.

## Time model and result order

For zero-based user index `i`, account creation is `starts_at + i *
account_spacing`. Payment index `j` occurs at `account_created_at +
first_payment_delay + j * payment_spacing`. Its terminal event occurs at attempt
time plus `terminal_delay`. Events are planned in user order, then payment order
(attempt before terminal), sorted by timestamp and stable planning ordinal, and
emitted while the virtual clock advances monotonically. Equal timestamps retain
planning order. `produced_at = occurred_at = SimulationRecord.generated_at`.

Result users and devices follow allocation order, transactions and attempts
follow deterministic user/payment creation order, and event records follow
simulation generation order. The output is in memory only.

## Production events

Every user emits `account.created` with its device ID. Every payment emits
`payment.attempted` and exactly one terminal event: `payment.failed` or
`transaction.completed`. The two payment events share a readable deterministic
trace ID. Each event uses the production V1 payload and passes
`validate_fraud_event`. CP02 emits no `chargeback.received`.

## Reproducibility and event UUIDs

Exact reproduction needs the master seed, UTC-normalized simulation start,
canonical legitimate configuration, simulator version, Python 3.13 runtime,
and locked environment. The immutable result retains the kernel manifest and
scenario configuration. `LegitimateScenarioConfig.to_json()` uses sorted compact
JSON with normalized currency, float probability, and integer microsecond
durations. The simulator version remains **1**.

Event IDs are UUIDv5 in a fixed Argus simulation namespace. The UUID name is
the canonical JSON of kernel manifest plus scenario configuration, followed by
event type and logical subject ID. Thus the same run and logical event retain
one UUID; changing the seed, start, or behavior configuration identifies a
different simulated world. No wall time, OS entropy, or UUIDv4 is involved.

## Explicit absence

There is no fraud, card model, promo abuse, chargeback behavior, late production,
transport duplicate injection, Kafka publishing, load generation, ML, or label.
