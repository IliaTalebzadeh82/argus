# Deterministic simulation kernel (Phase 03 / Checkpoint 01)

## Purpose and reproducibility

`argus.simulation` is a pure foundation for later synthetic-world generation. For
the same explicit integer seed, configuration, simulator version, supported
Python runtime, and ordered simulation calls, it produces the same records.
Phase 3's declared runtime is Python 3.13 (`pyproject.toml`); exact PRNG output
across arbitrary Python versions is **not** promised. Incompatible generation
semantics require incrementing `SIMULATOR_VERSION` (currently **1**) so a
historical seed does not silently acquire a new meaning. Run the same dependency
lock and runtime for reproducible experiments.

## Named randomness

`SimulationRandom` owns independent `random.Random` instances. A stream seed is
the integer value of `SHA-256(UTF-8(decimal master seed + ":" + namespace))`.
No Python `hash()` or module-global random state participates. Namespace names
are lowercase machine codes, optionally joined by `:` for hierarchy, such as
`users:user-000001`. A repeated lookup returns the **same stateful stream** and
continues its sequence. Asking for, or drawing from, another name cannot shift
it. Callers must use an explicit, stable order within each stream.

## Virtual time and identities

`SimulationConfig.starts_at` must be timezone-aware and is normalized to UTC.
`SimulationClock` starts there, never ticks on its own, accepts zero or positive
`timedelta` advancement, and rejects rewinding. Neither configuration nor clock
reads wall time. `IdentityAllocator` has one counter per lowercase entity kind;
its first `user` ID is `user-000001`. Padding is a fixed minimum width of six
digits, so IDs remain unique beyond 999999. Allocation order is an explicit
part of the simulation execution; IDs depend on that order, not on the seed.
Avoid allocating from unordered collections.

## Simulation records and manifest

`SimulationKernel.emit(value)` assigns a one-based, increasing simulation
sequence and captures current virtual time as `generated_at`. The record is
frozen, though an arbitrary object supplied as `value` is only as immutable as
that object. The sequence is generation order, **not** a Kafka offset, event ID,
or event time. A future `EventEnvelope.occurred_at` can precede the record's
`generated_at`; emitting a record never changes its value or an event's time.
The production envelope and its `produced_at` are separate concepts.

The immutable manifest contains only seed, normalized start time, and simulator
version. `to_json()` emits compact sorted-key JSON with a UTC `Z` timestamp.
Future datasets and streams can carry this manifest to identify their source.
It does not capture runtime RNG state or counters and is not a resume snapshot.

## Boundary

The kernel performs no filesystem, network, Kafka, Redis, PostgreSQL, or HTTP
I/O. It includes no fraud behavior, ML, or LLM integration. Future export and
publication belong in adapters outside the kernel.
