# Phase 03 review — synthetic world and workload

**Status: PASS.** Phase 3 meets its gate: a checked-in specification reconstructs a deterministic synthetic world, an inspectable artifact bundle, and a delivery schedule that CP05 published as a real Kafka event stream. The real Kafka → Redis run converged to the pure Phase-2 reference. This review closes Phase 3; it does not assert a supervised ML dataset or model.

## 1. What was built?

CP01 established the explicit seed, named random streams, virtual clock, deterministic allocation, and versioned manifest. CP02 used that kernel to create normal users, unique devices, payments, ordinary failures, and production-contract events. CP03 used the same primitives for account farms and coordinated ring behavior, while keeping shared-card, shared-promo, and ring relationships in simulator-only truth. CP04 combined the independent worlds with opaque, collision-free production IDs, then separated canonical logical events from late production and duplicate delivery attempts. CP05 made the complete workload reconstructible from `WorkloadSpec`, exported stable, checksum-covered artifacts, and played each scheduled attempt through the existing Kafka producer. These layers build from world facts to events to transport; a transport retry never creates a new world fact.

Here “reproducible dataset” means the **synthetic artifact bundle**: production entity snapshots, canonical event stream, delivery schedule, simulator-only generating truth, metadata/configuration, and checksums. It does not mean an ML feature matrix, target vector, train/test split, or model-ready supervised rows. Those are Phase-4 work.

## 2. What changed from the master plan?

The master plan named the synthetic populations, traffic shape, and reproducible dataset/event-stream gate without prescribing internal mechanisms. Named streams, an explicit virtual clock, reference-friendly allocation-order IDs, opaque scopes for mixed IDs, separate simulator truth, distinct logical events and delivery attempts, a versioned bundle, and a Kafka playback adapter make that gate precise. They preserve the planned production boundary and at-least-once assumptions. **No material architectural deviation.**

## 3. Why did it change?

No material architectural deviation. The elaborations solve concrete correctness problems: explicit stream ownership prevents unrelated draws from shifting behavior; virtual time excludes wall-clock variation; opaque scopes prevent mixed-world collisions without revealing cohorts; separate truth prevents accidental online evidence leakage; delivery records make duplicate attempts distinguishable from business facts; stable bytes and checksums permit independent artifact verification; and playback proves that the pure schedule can reach the real pipeline.

## 4. What failed?

**Design/correctness discoveries.** Independent standalone scenarios both allocate IDs such as `user-000001`, so composition needed disjoint scopes. A global mutable RNG would couple unrelated actors. Exposing ring/card/promo truth in production IDs or payloads would leak the generating scenario. Logical duplication belongs at the transport-attempt layer. The simulator's total schedule is not a Kafka-wide consumption-order guarantee. Phase-2 identity compares `produced_at`, so different production-delay variants are alternate histories and cannot share one projector namespace.

**Implementation/tooling.** Early checkpoints corrected minor Ruff/format issues and one Pydantic warning-producing test assertion. CP05 corrected a verifier bug that compared ISO timestamps lexically despite variable-width fractions, then reran checks successfully. These fixes left no known Phase-3 correctness defect. The upstream Starlette/AnyIO deprecation warning remains outside this phase.

## 5. What was learned?

### Determinism, identity, and baseline

The reproducibility key is **same seed + same complete configuration + same simulator version + Python 3.13 and locked dependency environment**. Python PRNG sequences are not promised across arbitrary runtimes. The seed is required, the simulator owns the random generators, and no hidden wall-time or entropy input enters the pure run.

One global RNG would let a new user or new draw shift every later value. Per-user amount, merchant, outcome, and fraud chargeback streams isolate behavior dimensions. Event-local lateness selection/delay and duplicate selection streams isolate transport faults. This lets an experiment change one dimension without silently perturbing another; complete scenario configuration can still remint event UUIDs by design. `SimulationClock` starts at configured aware UTC time and advances only by explicit nonnegative steps: simulation time is independent of wall time.

Standalone IDs follow per-kind allocation order, not seed. Both standalone scenarios can therefore create `user-000001`; these are distinct people and cannot share one mixed production ID. Mixed composition inserts deterministic opaque scope digests, keeping identifiers disjoint and stable as the other cohort grows. A prefix such as `fraud-user-*` would reveal the generating class. The legitimate baseline models one user with one unique device, ordinary successes and failures, and `accounts_on_device = 1`. Payment failure alone is not fraud.

### Truth, observability, and causality

Ring membership, shared synthetic card, shared promo, and account-farm relationships are generating truth known to the simulator. They do not automatically become online evidence, `RiskSignal`s, features, targets, or authoritative labels. Current production facts/rules can see shared devices, payment velocity, failed-payment velocity, and a later `chargeback.received` fact; they cannot directly see the synthetic card, promo, or ring relationship. This boundary prevents the model or decision path from learning an answer unavailable in production. A chargeback follows a payment attempt and completed transaction as a later outcome event. It does not retroactively modify the original event.

### Facts, events, and delivery

A world fact produces one canonical `EventEnvelope` and `event_id`; one or more `DeliveryRecord`s reference it. Attempt 1 and deliberate attempt 2 contain the exact same complete envelope. They represent separate transport attempts, not two payments. `occurred_at` says when the fact happened, `produced_at` when the producer emitted it, and `deliver_at` when the simulator attempts transport; a late event can satisfy `occurred_at < produced_at <= deliver_at`. CP04 changes `produced_at` for selected events without changing `occurred_at`, `event_id`, payload, or world truth in that traffic history. Because Phase-2 identity includes `produced_at`, alternate production-delay histories must use separate projection namespaces.

An event A can occur before B while B is delivered first. Phase-2 feature windows use `occurred_at`, deduplicate by logical identity, and converge under such order inversions. Traffic configuration shapes publication and attempts; it does not rewrite underlying world facts. A delivery schedule is a virtual total order. Kafka preserves order inside a partition, not one global order across the three partitions, so correctness does not depend on global replay order.

### Artifact and execution boundary

`WorkloadSpec`, versioned metadata, stable JSON/JSONL, UTC timestamps, and ordered SHA-256 checksums make a run reconstructible and inspectable. No wall-clock export metadata enters bytes. `production/`, `events/`, and `transport/` hold production-visible data and schedule metadata; `truth/` holds generating relationships and is never an input to production event publication. Bundle format version 1 describes file layout, simulator version 1 describes generation semantics, and event contract version 1 describes wire messages. These versions can change independently.

Playback issues one explicit producer call per `DeliveryRecord`: 58 logical events become 84 deliveries and 84 Kafka records, including 26 deliberate duplicates. Producer idempotence protects retries of one produce call; it does not erase two deliberate calls for the same event. In CP05, the real three-partition run yielded 58 Redis `APPLIED` and 26 `DUPLICATE` results. Redis reached `READY`; all eight generated users' final snapshots matched the pure reference from 58 unique canonical events. This is at-least-once transport with idempotent feature effects, not exactly-once execution.

## 6. What metrics were observed?

Final offline suite: **265 passed**, including **89 focused Phase-3 tests**; one upstream deprecation warning. Simulator version **1**; bundle format version **1**. Demo: **8 users, 5 devices, 24 transactions, 24 payment attempts; 1 fraud ring, 12 card uses, 4 promo redemptions; 58 logical events, 84 scheduled deliveries, 26 duplicate deliveries, 28 late logical events**. Bundle: **10 checksum-covered payload files**. CP05 real local integration: **3 Kafka partitions, 84 observed records, 58 Redis `APPLIED`, 26 `DUPLICATE`, 8 user snapshots equal to the pure reference**. These are correctness counts, not throughput or capacity measurements.

## 7. What technical debt was introduced?

**Deliberately deferred design:** playback resume/checkpointing, streaming large schedules instead of holding them in memory, richer legitimate distributions, additional fraud archetypes, real production card/promo contracts, and workload scaling. These were outside the Phase-3 gate.

**Reproducibility boundary:** exact Python PRNG results are scoped to Python 3.13 and the locked environment; version 1 records generation semantics.

**Local development limits:** the proof used a small demo, a single local Kafka broker with replication factor 1, and synchronous publish/flush. It makes no performance claim.

## 8. Is Phase 4 still the correct next phase?

Yes. Phase 3 supplies a reproducible raw synthetic world, separated generating truth, and real event-stream evidence. Phase 2 supplies online feature semantics. No additional mandatory synthetic-data checkpoint is needed before the planned predictive fraud model phase. Phase 4 must choose a prediction unit, prediction timestamp, information available at that timestamp, target/outcome horizon, and leakage rules before constructing supervised rows. It must **not** simply flatten `FraudRingTruth -> is_fraud = 1`. Simulator truth supports controlled experiments, but time causality governs dataset construction. Delayed operational label maturation remains a Phase-6 concern. No Phase-4 design or implementation is made here.

## 9. Does the master plan need an ADR/update?

No. Named streams, simulator-only truth, opaque scoping, the logical-event/`DeliveryRecord` distinction, bundle separation, and Kafka playback are faithful elaborations of the existing Phase-3 reproducibility and event-stream goal. None changes authoritative state, production contracts, or phase order. This review records the operationally important contracts; neither an ADR nor a master-reference edit is warranted.

## Phase 3 Reproducibility Contract

Given the same `WorkloadSpec` (including explicit seed and UTC start), simulator version 1, Python 3.13 runtime, and locked dependency environment, Argus reproduces the same synthetic world, production entity snapshots, canonical events, simulated delivery schedule, and exported bundle bytes. The checked-in demo spec parses and serializes identically; two independent generations compare equal in memory. Two exports to separate temporary directories had the same 11 relative files and bytes, identical `checksums.sha256`, and both passed `verify_bundle`; all 10 payload checksums matched. The files were removed with the temporary directories. Kafka playback reproduces the scheduled set of deliveries, not a global cross-partition consumption order or a wall-clock execution trace.

## Synthetic Ground Truth Contract

Ring/card/promo/account-farm relationships are generating truth. They are not automatically online facts, `RiskSignal`s, model features, targets, or authoritative production labels. Shared-device facts are production-visible. A chargeback is a later production-visible outcome; interpreting it as a model label requires a future dataset/label decision with an explicit time boundary.

## Phase 3 Gate

1. **Explicit seed?** It makes stochastic generation replayable and auditable.
2. **Why not one global RNG?** An unrelated draw would shift later behavior everywhere.
3. **Named stream?** It gives stable ownership and locality to a random dimension.
4. **Virtual time?** A repeat must not depend on when the process runs; the clock moves explicitly.
5. **Entity IDs?** Standalone per-kind allocation order; mixed worlds add deterministic opaque scopes.
6. **Why standalone collisions?** Both independent allocators start at the same first ID.
7. **Why not `fraud-user-*`?** The identifier would leak the generating cohort.
8. **Simulator-only truth?** The ring, card, promo, and farm relationships that generated the scenario.
9. **Shared card online?** There is no production card fact or feature contract exposing it.
10. **Failure equals fraud?** No; ordinary legitimate payments can fail.
11. **Logical event?** One canonical envelope and event ID for one business fact.
12. **Delivery attempt?** One scheduled transport of that same envelope.
13. **Multiple deliveries?** At-least-once transport and deliberate duplicate injection can repeat a fact.
14. **`occurred_at`?** The fact's business/event time.
15. **`produced_at`?** The time the producer emitted the event.
16. **`deliver_at`?** The simulator's virtual transport-attempt time.
17. **Order inversion?** Delay A enough that later-occurring B arrives first.
18. **Same `event_id`?** Retries must preserve logical identity for deduplication.
19. **Traffic vs world?** Traffic changes production delay/attempts, not underlying world facts.
20. **Reproducible export?** Complete spec/version, stable ordering/encoding, no wall time, checksums.
21. **Why separate `truth/`?** Production input must not reveal generating answers.
22. **Three versions?** Layout, generation algorithm, and production wire schema evolve separately.
23. **58 to 84?** Each of 58 events has attempt 1; 26 have a second deliberate attempt.
24. **Kafka global order?** Only within-partition order is guaranteed.
25. **Redis convergence?** Identical event IDs return `DUPLICATE`; 58 unique effects remain.
26. **ML absent?** No feature matrix, target vector, split, training, model, or online score was built.

## Architecture invariants and scope audit

All Phase-3 invariants are confirmed:

- [x] Explicit seed, wall-independent virtual time, simulator-owned randomness, stable named streams, and locality for unrelated actors.
- [x] Separate legitimate baseline; failure is not fraud; coordinated ring truth is simulator-only; production payloads omit ring/card/promo truth while shared devices remain visible.
- [x] Causal chargebacks, reproducible standalone worlds, collision-free opaque mixed IDs without cohort disclosure.
- [x] One canonical event per fact; traffic preserves world facts; lateness preserves `occurred_at`; duplicate attempts repeat the exact envelope; event-time and delivery order may differ; reference features converge.
- [x] Complete `WorkloadSpec` reconstruction; deterministic exported bytes; separated production/truth files; real production event wire contract; schedule references event IDs; verified checksums.
- [x] One Kafka publish per delivery, unchanged `user_id` keying, no claimed cross-partition global order, and real Redis/reference convergence.
- [x] No Decision API behavior change, ML training dataset/model, or watermark/lateness-completeness policy.

Scope audit found no ML model, training pipeline, feature matrix, train/test split, flattened `is_fraud` target, watermark, allowed-lateness policy, new Decision API behavior, production card/promo schema, graph engine, playback checkpoint database, or performance benchmark claim.

## Closure validation

`uv sync --locked` passed (33 resolved, 31 checked). `make check` passed Ruff lint/format and **265** offline tests. `docker compose config --quiet` and `git diff --check` passed. The independent demo round-trip, generation, export, checksum, and bundle verification passed as described above. CP05's real Kafka/Redis evidence supplies the integration gate; it was not rerun for this documentation-only closure. `docker compose ps --format json` showed no running project services.
