# Base event contract

An **event** is a logical fact. A **message** is a transport representation or
delivery of that fact. Kafka is a future transport; the envelope has no broker
dependency. A producer supplies one UUID `event_id` for the logical event and
reuses it on publish retries. Broker redelivery keeps that identity too.

| Field | Meaning |
| --- | --- |
| `event_id` | Producer-supplied UUID identifying one logical event. |
| `event_type` | Non-empty stable fact name; convention: `<subject-or-concept>.<past-tense-fact>` (for example, `account.created`). |
| `event_version` | Positive integer, starting at 1. |
| `occurred_at` | Event time: when the fact happened in the source/domain world. |
| `produced_at` | Time the integration event was produced. |
| `producer` | Non-empty stable logical component name, not a process, host, or container ID. |
| `trace_id` | Non-empty opaque cross-boundary correlation value. Its tracing format is intentionally open in Phase 0. |
| `subject_id` | Non-empty opaque identity of the primary entity or aggregate the event concerns. |
| `payload` | A concrete Pydantic model supplied as `EventEnvelope[PayloadType]`. |

Both timestamps require timezone information, normalize to UTC, and serialize
as unambiguous ISO 8601 JSON timestamps with `Z`. Consumer **processing time**
is separate and is not carried by this envelope. `produced_at` need not follow
`occurred_at`: clock skew, backfills, historical imports, and reconciliation can
produce the opposite ordering.

The pair `(event_type, event_version)` identifies a specific payload contract.
After publication, neither the meaning nor required wire shape of that version
may change. Breaking changes require a new `event_version`. Unknown envelope
fields are rejected, so additive envelope changes also require deliberate
contract evolution rather than being silently ignored. No registry or migration
mechanism is defined yet.

Use `EventEnvelope[PayloadType].model_dump_json()` and
`EventEnvelope[PayloadType].model_validate_json(...)` for a typed JSON round
trip. The envelope is frozen after construction. A nested payload is only as
immutable as its own model and contained values; freezing the envelope alone
does not deeply freeze them.

Future consumers must account for at-least-once delivery. They will deduplicate
by logical `event_id`, not by Kafka offset alone; no deduplication mechanism is
implemented here. `subject_id` may inform future partition keys when ordering
is subject-scoped, but this contract makes no partitioning decision.
