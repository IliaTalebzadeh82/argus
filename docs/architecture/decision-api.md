# Phase 1 Decision API

`POST /v1/decisions/payment` accepts a `context` containing a user, transaction,
selected payment attempt, ordered devices, and ordered caller-computed risk
signals. The client cannot supply a final action, reason, or provenance. Invalid
relationships and facts receive HTTP 422.

The request passes through the versioned Phase-1 `RuleEngine`, then the
`ConservativeDecisionPolicy`, then one atomic PostgreSQL audit transaction.
Demonstration thresholds, source, and rule membership live in
`apps/decision_api/service.py`. Every change to them requires a rule-set version
bump. The policy is the sole action-composition implementation. Missing or
ambiguous rule evidence is `INDETERMINATE` and may produce a business `REVIEW`;
it is not a database error.

`Idempotency-Key` is an opaque HTTP request identity, separate from decision,
transaction, and payment IDs. The validated context is serialized as canonical
JSON and SHA-256 hashed. UTC timestamps and currency are normalized by the
domain model; object keys are sorted while device and signal order is retained.
PostgreSQL atomically claims the unique key and records the decision. A replay
with the same fingerprint returns the stored decision with `replayed: true`.
Different content for the same key returns HTTP 409 `IDEMPOTENCY_KEY_REUSED`.
The database uniqueness constraint serializes concurrent claims, and a deferred
foreign key enforces that a committed claim references a recorded decision.
A failed audit write rolls the claim back. There are no automatic write retries.

The service generates a UUID and UTC time at the application boundary through
injectable providers and passes them into pure policy logic. HTTP success only
follows transaction commit. Authoritative fact conflicts return HTTP 409
`AUTHORITATIVE_FACT_CONFLICT`. PostgreSQL connection failure returns HTTP 503
`DATABASE_UNAVAILABLE`; it never creates an ALLOW or other synthetic decision.

`/health/live` checks only process responsiveness. `/health/ready` checks actual
PostgreSQL connectivity and required decision schema columns. The SQLAlchemy
engine is created during app startup with `pool_pre_ping` and disposed on
shutdown. Migrations are an explicit deployment step; an unmigrated API may be
live but not ready.

Current dependencies: Decision API → PostgreSQL; Investigator API → none.
Redis, Kafka, ML, and LLM do not participate in this decision path.
