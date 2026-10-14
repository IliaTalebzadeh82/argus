# Feature freshness boundaries (Phase 02 / Checkpoint 05)

Three different statements must remain separate:

| State | Current meaning | What it does not establish |
| --- | --- | --- |
| Redis `READY` | A projection exists, its rebuild finished through a captured Kafka cutoff, and Redis can answer feature queries. | Continuous catch-up with the live group. |
| Kafka group lag | For each partition, broker high watermark minus the next committed processing offset. The diagnostic totals these pending records. | Completion of event-time history or atomicity with a decision request. |
| Event-time completeness | A claim that no additional qualifying fact with `occurred_at <= T` can arrive for a query at `T`. | No such contract exists in Phase 2. |

The operator-only `make feature-lag` command uses Kafka Admin APIs without joining the live consumer group. It reports topic, group, per-partition retained low offset, high offset, committed offset, pending records, and total pending records. High and committed offsets both mean the *next* record position, so pending is `high - committed`, with no subtraction of one. For the live group's `earliest` start policy, a missing commit remains `null` and the estimated retained backlog is `high - low`. Missing commit and an actual commit at low are distinct states. Offsets outside the retained `[low, high]` range fail the probe; they are not clamped. This is an instantaneous diagnostic, not a consistent cross-partition snapshot or an availability gate. A producer or worker can advance offsets immediately after inspection.

In the [CP05 local campaign](../experiments/phase-02-lag-freshness.md), Redis stayed `READY` and the Decision API stayed ready while 30 Kafka records were pending. The API read valid Redis values that were behind the broker's history. After catch-up, a new decision changed action, while replay of the original idempotency key returned the PostgreSQL historical decision. PostgreSQL is decision/audit authority; Redis is derived current feature state.

The late-event experiment began and ended with zero group lag, yet historical `payments_10m` changed after new records with earlier `occurred_at` arrived. A watermark would require an upstream claim about event-time progress and allowed lateness; broker offset progress alone cannot supply it. The request and its `payment.attempted` event are separate flows: a decision can precede its own event's projection. Argus has no correlation barrier to decide whether that event is already included, so request-time increments would risk double counting.

The API currently reads only PostgreSQL and Redis. This checkpoint makes no readiness, fraud policy, projection, schema, or consumer processing change. Future freshness policy requires a separately defined guarantee and measured availability trade-off.
