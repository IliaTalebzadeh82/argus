# Core fraud domain (Phase 01 / Checkpoint 01)

These Pydantic objects are immutable snapshots of facts available to one deterministic evaluation. They validate local invariants and identifiers, but perform no rule evaluation or feature computation. References are opaque strings. Every timestamp is aware and normalized to UTC; naive times are rejected.

## Relationships

- One user can have many transactions (`Transaction.user_id`).
- One transaction can have many payment attempts (`PaymentAttempt.transaction_id`). A commercial action and a payment try are different facts; retries must remain distinguishable.
- Users and devices are many-to-many observations. A device has its own identity and first-seen time, no owner. A `DecisionContext` can contain devices observed for its user; the same device can appear in another user's context. It does not prove ownership.

`DecisionContext` checks the user and transaction references it actually has. It cannot establish cross-entity time ordering or ownership from absent data. It holds tuples of devices and signals, without a nested persistence graph.

## Values and evidence

`Money` uses nonnegative integer minor units, including zero, and normalized three-letter ASCII currency codes. This avoids binary floating-point amounts; currency code validation does not verify membership in a currency registry or perform FX conversion.

A `RiskSignal` is one immutable, scalar observation for an evaluation: stable machine-readable code, typed boolean/integer/finite float/string value, UTC observation time, and logical source. The source identifies the computation or producer, not a host. It does not compute features, assert fraud, or decide an action. Structured/nested values are outside this checkpoint.

`Decision` records a historical action and one or more machine-readable reason codes. These can be traced to deterministic evidence as rules are introduced. Prose is not authoritative evidence. The model has no mutable investigation notes or generated explanation. Corrections will require separate records, not rewriting a historical decision. `subject_id` names the evaluated transaction in the current context; persistence and decision creation come later. Rule, policy, feature, model, and trace metadata are deferred until their concrete semantics and producers exist.

## Boundary

Domain immutability means these in-memory snapshots cannot be edited; it does **not** mean database rows can never change. Persistence policy is a separate concern. The domain objects know nothing about PostgreSQL, Redis, Kafka, FastAPI, ML, or LLMs. The Decision API remains liveness-only.
