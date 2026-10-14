# Mixed synthetic workload (Phase 03 / Checkpoint 04)

## Composition and world truth

`run_mixed_workload` runs the unchanged legitimate and fraud generators on separate
kernels with the same manifest. Each kernel gets an opaque twelve-digit hex
identity scope derived from SHA-256 of a fixed internal scenario namespace.
The allocator inserts that scope into every entity ID. Standalone kernels use
the original unscoped IDs. This keeps production IDs disjoint without exposing
cohort names; the scope algorithm is versioned in canonical mixed-world metadata.
Separate kernels preserve each population's random streams and behavior when
the other population grows. Each child result retains its scenario config and
facts. Combined production users, devices, transactions, and attempts are
stable tuples. Fraud ring membership, shared cards, and promo relationships
remain only in the fraud child result; they are absent from production events.

## Logical, production, and delivery time

`canonical_events` contains each production fact once. `event_id` is its logical
identity. `occurred_at` is the business event time used by Phase 2 feature
windows. `produced_at` is the publication time in the canonical envelope.
For selected events, a deterministic nonnegative delay makes
`produced_at > occurred_at`; other events have equal times. A zero selected
delay is also allowed. This changes neither the underlying world nor the
logical event ID.

`delivery_records` is a simulator-only schedule. Every canonical event has an
attempt 1 at `produced_at`; selected events have one attempt 2 after the
configured delay. Both attempts reference the exact same complete envelope.
`deliver_at` and the one-based `sequence` describe virtual transport order,
not Kafka offsets, partitions, or event identity. Sorting by delivery time and
stable planning ordinal preserves attempt 1 before attempt 2 for equal-time
ties. Production delay can make a later occurrence arrive first: out-of-order
event time is expected.

## Determinism and traffic shape

The result retains the simulation manifest, both scenario configurations, and
traffic configuration in canonical JSON metadata. Traffic uses named
event-local streams keyed by the scoped subject ID and event type, with separate late selection,
delay, and duplicate selection dimensions. Changing duplicate settings cannot
change canonical events or lateness. Changing lateness settings cannot change
world facts or duplicate selection. The summary counts logical events,
delivery attempts, duplicates, and late events; it includes time bounds and
ordered fixed 60-second UTC delivery buckets. Closely spaced fraud activity
can occupy denser buckets than the legitimate baseline.

## Phase 2 compatibility and alternate histories

The reference projector applies each canonical event once, or accepts its
delivery attempts in schedule order. First attempts return `APPLIED`; exact
redeliveries return `DUPLICATE`. Final feature snapshots agree because the
projector deduplicates on full event identity and calculates windows from
`occurred_at`, regardless of delivery order. It includes `produced_at` in the
canonical identity. Therefore two variants of the same logical world with
different production delays are **alternate experimental histories** and
must not be merged in one downstream projection namespace.

This generator performs no Kafka execution, filesystem export, database or
HTTP I/O, real-time sleeping, ML labeling, or watermark policy.
