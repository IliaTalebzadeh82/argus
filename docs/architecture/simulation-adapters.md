# Simulation adapters (Phase 03 / Checkpoint 05)

## Boundary and reconstruction

`SimulationKernel`, both scenarios, and `run_mixed_workload` remain pure. `WorkloadSpec` holds the existing typed simulation, world, and traffic configs. Its canonical JSON uses sorted compact keys, UTC ISO-8601 start time, and integer microsecond durations. Parsing it reconstructs the same typed values and mixed result under simulator version 1, Python 3.13, and the locked environment. The checked-in `configs/simulation/phase-03-demo.json` exercises legitimate and fraud populations, payments, chargebacks, lateness, and duplicates.

## Bundle

Run without infrastructure:

```bash
uv run --locked python -m argus.simulation.cli export --spec configs/simulation/phase-03-demo.json --output /tmp/argus-phase03
```

The target must not exist. Export writes a temporary sibling, verifies it, then renames it to the target on the same filesystem. It will not mix old and new histories. `metadata.json` contains bundle format version **1**, simulator version **1**, the manifest, full spec, and counts. Bundle version describes file layout; simulator version describes generation semantics; event version describes the production wire contract. No wall-clock or machine-specific values enter the bundle.

`production/` contains users, devices, transactions (integer minor-unit money and currency), and payment attempts. `events/canonical-events.jsonl` contains exactly one production wire event per logical ID using `serialize_fraud_event`. `transport/delivery-schedule.jsonl` contains sequence, virtual delivery time, attempt, and a reference to the canonical event ID. `truth/` contains fraud rings, card uses, and promo redemptions only. These artifacts preserve the synthetic world's generating truth for later experiment design. Dataset/label construction remains a separate Phase-4/Phase-6 decision. No flattened fraud target is exported.

JSON/JSONL uses UTF-8, sorted compact keys, UTC timestamps, stable result order, and newline terminators. `checksums.sha256` lists all payload files in relative-path order. `verify_bundle(path)` checks the exact file set, hashes, counts, canonical event decoding, delivery references and attempts, and truth entity references. Identical workloads exported to different target paths produce identical bytes.

## Playback

Run with reachable Kafka and an explicitly provisionable topic:

```bash
uv run --locked python -m argus.simulation.cli publish --spec configs/simulation/phase-03-demo.json --bootstrap-servers localhost:9092 --topic argus.fraud-events.v1 --unpaced
```

The CLI calls the existing `ensure_fraud_topic`, then passes each `DeliveryRecord.event` to `KafkaFraudEventProducer.publish` in sequence. This is independent of bundle export. The producer uses `user_id` as key, so one user's records route consistently. Each duplicate delivery makes a separate application-level publish call with the exact same envelope; producer idempotence protects broker retries of one call and does not deduplicate intentional calls.

Unpaced playback publishes as fast as acknowledged calls permit. `--speedup 60` means one virtual minute per real second. Paced playback anchors virtual elapsed time at the first delivery and real elapsed time at `time.monotonic()`. It waits for absolute scaled targets so publish latency does not accumulate drift. Neither mode mutates event timestamps or IDs. The simulator has one deterministic global publication schedule, but Kafka with multiple partitions guarantees ordering only within each partition. Cross-partition consumption can differ from the global sequence.

A publish failure stops playback and raises. There is no resume offset; rerunning against the same downstream namespace can add duplicates. The real CP05 test publishes the isolated demo topic, checks broker count/keys/duplicates, rebuilds an isolated Redis projection from the Kafka history, and compares final snapshots with the pure canonical reference. This is a semantic integration proof, not a throughput benchmark. No Decision API load, ML dataset, watermark, or producer batching is included.
