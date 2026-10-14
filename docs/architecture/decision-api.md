# Phase 2 Decision API

`POST /v1/decisions/payment` accepts `facts`: `UserAccount`, `Transaction`,
`PaymentAttempt`, supplied `devices`, and an explicit `observed_device_id` that
must name a supplied device or be null. Caller signals, action, reasons, and
rule/policy metadata are rejected. Argus queries Redis at
`payment_attempt.attempted_at`, maps the READY snapshot to
`redis_features_v1` risk signals, then applies the unchanged rules and policy.
The rule-set configuration is version 2 because its evidence source changed;
individual rule and policy versions remain 1.

The feature `as_of` is the payment attempt's event time. `decided_at` is when
Argus creates the judgment and may be later. Missing observed device omits
`accounts_on_device`; its rule is indeterminate and policy may return REVIEW.
A known zero from a READY projection is valid evidence. Redis failure,
UNINITIALIZED, or REBUILDING prevents a new judgment with 503
`FEATURES_UNAVAILABLE`.

PostgreSQL is authoritative for decision history. The service claims the key
and facts-only fingerprint in a PostgreSQL transaction before reading Redis.
A committed same-key/same-facts replay returns the stored decision without
Redis, including during an outage or after Redis values change. Changed facts
return 409. A failed feature read rolls back the new claim. The transaction
remains open during the read to serialize concurrent idempotency; Redis and
PostgreSQL do not share a distributed transaction. Generated signals, including
code, value, source, and observed time, are copied into `DecisionRecord` in
PostgreSQL, so historical explanation does not depend on Redis retention.

`/health/live` tests only the process. `/health/ready` tests PostgreSQL decision
schema, Redis connectivity, and projection lifecycle READY. READY means
initialized and queryable; it does not prove zero Kafka consumer lag or arrival
of all late events at the chosen `as_of`. The API does not inspect Kafka.

```text
Decision API -> PostgreSQL, Redis
Feature Worker -> Kafka, Redis
Investigator API -> none
```

The API constructs and closes its database engine and Redis client in lifespan.
It requires `ARGUS_DATABASE_URL` and `ARGUS_REDIS_URL`; optional
`ARGUS_FEATURE_NAMESPACE` defaults to the version-one production namespace.
