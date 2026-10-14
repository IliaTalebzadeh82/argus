# Coordinated synthetic fraud world (Phase 03 / Checkpoint 03)

## Archetype and visibility

`fraud_world.py` creates rings of distinct accounts sharing one production `Device`
snapshot per ring. Each account emits `account.created` with that device ID. The
production stream then records ordinary `payment.attempted`, `payment.failed`,
`transaction.completed`, and later `chargeback.received` facts. No event carries
ring membership or a fraud flag. Production IDs are ordinary opaque `user-*`,
`device-*`, `payment-*`, `transaction-*`, and `chargeback-*` values.

Each ring also has one simulated card and one promo code. `SyntheticCardUse`
records each payment's user and transaction; `SyntheticPromoRedemption` records
the first payment per member. These immutable relationships, plus ring and farm
identities, exist **only in the scenario result**. Card use and promo reuse
cross multiple accounts when payments exist. There are no production card or
promo contracts yet, so current Decision API/rules cannot see these facts.

The shared device *is* visible: the Phase 2 reference projector reports
`accounts_on_device` across the ring accounts. Closely timed attempts and
failures can raise `payments_10m` and `failed_payments_1h`. Current rules can
observe those three features, but cannot observe shared card, promo reuse,
ring membership, or a chargeback before it occurs. Fraud truth and current
rule detectability are separate; settings need not trigger every rule.

## Time, randomness, and order

For zero-based ring `r`, its start is `starts_at + r * ring_spacing`. Member
`i` is created at ring start plus `i * account_spacing`. Its payment `j` is
attempted at account creation plus `first_payment_delay + j * payment_spacing`.
The terminal event is at attempt plus `terminal_delay`; a selected chargeback
is at successful completion plus `chargeback_delay`. Failed payments are never
eligible. A chargeback shares the payment trace, has its own allocated ID, and
states only that a later outcome occurred. It does not retroactively label the
earlier payment. Even with zero delay, stable planning order puts completion
before its chargeback.

Per-user streams are `fraud-payments:{user_id}:amount`, `:merchant`, `:outcome`,
and `:chargeback`. Draws for one dimension cannot shift another. Adding a ring
at the end leaves earlier rings' IDs, relationships, timing, amounts, merchant
choices, and outcomes intact. UUIDv5 event IDs deliberately include the
canonical **whole** manifest and scenario configuration, followed by event
type and logical subject; adding a ring therefore changes event UUIDs.
The event type separates payment attempt/failure IDs, and the chargeback has
its own subject ID. This matches the legitimate scenario's UUID mechanism.

Events are planned in ring, member, payment order and emitted by
`(occurred_at, planning_ordinal)` so the virtual clock only advances. Result
rings and members follow allocation order; card uses follow transaction
creation order; promo redemptions follow ring/member order; event records
follow generation order. `produced_at = occurred_at = generated_at`.

Reproduction requires the manifest's seed, UTC start and simulator version 1,
canonical `FraudScenarioConfig.to_json()`, Python 3.13, and the locked
environment. The result retains the manifest and immutable config. Simulator
knowledge of the generating scenario is **not** online knowledge and does not
automatically become an ML feature or target. Phase 4 owns dataset construction;
Phase 6 owns delayed label maturation.

This checkpoint has no mixed workload, late production, transport duplicates,
rate shaping, file export, Kafka publication, ML, labels, graph processing,
RiskSignal injection, or infrastructure I/O.
