# PostgreSQL decision audit (Phase 01 / Checkpoint 04)

PostgreSQL is authoritative for recorded Phase-1 transaction facts and decision
history. A stored decision ID reconstructs its user, transaction, selected
payment attempt, ordered devices and signals, ordered rule evaluations and
copied evidence, final action, ordered reasons, and policy/rule-set provenance.
Redis and Kafka have no role in this checkpoint.

## Domain and database boundary

Pydantic domain snapshots are not database rows or SQLAlchemy tables. Explicit
SQLAlchemy Core mappings preserve the pure domain and hydrate through its
validators. JSONB is used only for scalar signal values with an accompanying
`value_type`; it is not an opaque decision document or general feature store.
All timestamps use `TIMESTAMP WITH TIME ZONE` and hydrate to UTC.

## Atomic recording and immutable facts

The caller owns a transaction, normally `with engine.begin() as connection`.
The repository writes one entire `DecisionRecord` through that connection and
never commits partway. A raised conflict or SQL error requires the caller to
roll back. Shared user, device, transaction, and payment facts are inserted if
absent, reused when equivalent, and rejected with `PersistenceConflict` when
an existing identity has different immutable fields. Decisions are insert-only:
there is no update/delete API, and duplicate decision IDs fail. API idempotency
uses a second table and migration; the service owns the transaction containing
both the claim and complete audit record.

## Evidence and order

Decision-time signals include nonmatches as well as matches. Each rule
comparison stores its own evidence snapshot, so it does not rely on Python
object identity or on later signal recomputation. Foreign keys keep evidence
attached to its evaluation and decision. Ordinals preserve device, context
signal, evaluation, evidence, and final reason order; reads use `ORDER BY`.
A device has no owner field, and a transaction can have multiple payment
attempts. The decision references the specific attempt evaluated.

## Current boundary

There are no ML scores, model versions, feature snapshot IDs, Kafka metadata,
or LLM outputs in this schema. The Decision API now depends on PostgreSQL for every successful decision.
See `decision-api.md` for replay and failure semantics.
