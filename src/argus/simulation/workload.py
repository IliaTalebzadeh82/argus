"""Pure mixed world and deterministic transport schedule."""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argus.domain.models import Device, PaymentAttempt, Transaction, UserAccount
from argus.events.envelope import EventEnvelope
from argus.events.fraud import FraudPayload
from argus.simulation.config import SimulationConfig
from argus.simulation.fraud_world import (
    FraudScenarioConfig,
    FraudScenarioResult,
    run_fraud_scenario,
)
from argus.simulation.kernel import SimulationKernel, SimulationManifest
from argus.simulation.legitimate import (
    LegitimateScenarioConfig,
    LegitimateScenarioResult,
    run_legitimate_scenario,
)
from argus.simulation.random import SimulationRandom

_IDENTITY_STRATEGY = "sha256-opaque-scope-v1"


@dataclass(frozen=True, slots=True)
class MixedWorldConfig:
    legitimate: LegitimateScenarioConfig
    fraud: FraudScenarioConfig

    def __post_init__(self) -> None:
        if not isinstance(self.legitimate, LegitimateScenarioConfig):
            raise TypeError("legitimate must be a LegitimateScenarioConfig")
        if not isinstance(self.fraud, FraudScenarioConfig):
            raise TypeError("fraud must be a FraudScenarioConfig")

    def to_json(self) -> str:
        return json.dumps(
            {
                "fraud": json.loads(self.fraud.to_json()),
                "identity_strategy": _IDENTITY_STRATEGY,
                "legitimate": json.loads(self.legitimate.to_json()),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class TrafficBehaviorConfig:
    late_event_probability: float
    min_production_delay: timedelta
    max_production_delay: timedelta
    duplicate_delivery_probability: float
    duplicate_delivery_delay: timedelta

    def __post_init__(self) -> None:
        for name in ("late_event_probability", "duplicate_delivery_probability"):
            value = getattr(self, name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{name} must be finite and in [0, 1]")
            object.__setattr__(self, name, float(value))
        for name in (
            "min_production_delay",
            "max_production_delay",
            "duplicate_delivery_delay",
        ):
            value = getattr(self, name)
            if not isinstance(value, timedelta):
                raise TypeError(f"{name} must be a timedelta")
            if value < timedelta(0):
                raise ValueError(f"{name} must be nonnegative")
        if self.max_production_delay < self.min_production_delay:
            raise ValueError("production delay range is reversed")

    def to_json(self) -> str:
        microsecond = timedelta(microseconds=1)
        return json.dumps(
            {
                "late_event_probability": self.late_event_probability,
                "min_production_delay_us": self.min_production_delay // microsecond,
                "max_production_delay_us": self.max_production_delay // microsecond,
                "duplicate_delivery_probability": self.duplicate_delivery_probability,
                "duplicate_delivery_delay_us": self.duplicate_delivery_delay
                // microsecond,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    sequence: int
    deliver_at: datetime
    attempt: int
    event: EventEnvelope[FraudPayload]


@dataclass(frozen=True, slots=True)
class TrafficSummary:
    logical_event_count: int
    delivery_count: int
    duplicate_delivery_count: int
    late_logical_event_count: int
    earliest_occurred_at: datetime
    latest_occurred_at: datetime
    earliest_produced_at: datetime
    latest_produced_at: datetime
    earliest_deliver_at: datetime
    latest_deliver_at: datetime
    delivery_buckets: tuple[tuple[datetime, int], ...]


@dataclass(frozen=True, slots=True)
class MixedWorkloadResult:
    manifest: SimulationManifest
    world_config: MixedWorldConfig
    traffic_config: TrafficBehaviorConfig
    legitimate: LegitimateScenarioResult
    fraud: FraudScenarioResult
    users: tuple[UserAccount, ...]
    devices: tuple[Device, ...]
    transactions: tuple[Transaction, ...]
    payment_attempts: tuple[PaymentAttempt, ...]
    canonical_events: tuple[EventEnvelope[FraudPayload], ...]
    delivery_records: tuple[DeliveryRecord, ...]
    traffic_summary: TrafficSummary

    def metadata_json(self) -> str:
        return json.dumps(
            {
                "manifest": json.loads(self.manifest.to_json()),
                "world": json.loads(self.world_config.to_json()),
                "traffic": json.loads(self.traffic_config.to_json()),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


def _scope(name: str) -> str:
    return hashlib.sha256(f"argus:{_IDENTITY_STRATEGY}:{name}".encode()).hexdigest()[
        :12
    ]


def _summary(
    events: tuple[EventEnvelope[FraudPayload], ...],
    deliveries: tuple[DeliveryRecord, ...],
) -> TrafficSummary:
    buckets: dict[datetime, int] = {}
    for delivery in deliveries:
        bucket = delivery.deliver_at.astimezone(UTC).replace(second=0, microsecond=0)
        buckets[bucket] = buckets.get(bucket, 0) + 1
    return TrafficSummary(
        logical_event_count=len(events),
        delivery_count=len(deliveries),
        duplicate_delivery_count=len(deliveries) - len(events),
        late_logical_event_count=sum(
            event.produced_at > event.occurred_at for event in events
        ),
        earliest_occurred_at=min(event.occurred_at for event in events),
        latest_occurred_at=max(event.occurred_at for event in events),
        earliest_produced_at=min(event.produced_at for event in events),
        latest_produced_at=max(event.produced_at for event in events),
        earliest_deliver_at=deliveries[0].deliver_at,
        latest_deliver_at=deliveries[-1].deliver_at,
        delivery_buckets=tuple(sorted(buckets.items())),
    )


def run_mixed_workload(
    simulation: SimulationConfig,
    world: MixedWorldConfig,
    traffic: TrafficBehaviorConfig,
) -> MixedWorkloadResult:
    """Generate independent worlds, then assign event-local transport behavior."""
    if not isinstance(world, MixedWorldConfig):
        raise TypeError("world must be a MixedWorldConfig")
    if not isinstance(traffic, TrafficBehaviorConfig):
        raise TypeError("traffic must be a TrafficBehaviorConfig")
    legitimate = run_legitimate_scenario(
        SimulationKernel(simulation, identity_scope=_scope("legitimate")),
        world.legitimate,
    )
    fraud = run_fraud_scenario(
        SimulationKernel(simulation, identity_scope=_scope("fraud")), world.fraud
    )
    planned = tuple(
        sorted(
            (
                *(record.value for record in legitimate.event_records),
                *(record.value for record in fraud.event_records),
            ),
            key=lambda event: (event.occurred_at, event.event_id.hex),
        )
    )
    random = SimulationRandom(simulation.seed)
    events: list[EventEnvelope[FraudPayload]] = []
    scheduled: list[tuple[datetime, int, int, EventEnvelope[FraudPayload]]] = []
    for event in planned:
        # Subject IDs remain stable for appended population members even when
        # scenario-config changes intentionally remint the event UUIDs.
        name = f"traffic:{event.subject_id}:{event.event_type.replace('.', '-')}"
        delay = timedelta(0)
        if (
            random.stream(f"{name}:late-selection").random()
            < traffic.late_event_probability
        ):
            minimum = traffic.min_production_delay // timedelta(microseconds=1)
            maximum = traffic.max_production_delay // timedelta(microseconds=1)
            delay = timedelta(
                microseconds=random.stream(f"{name}:late-delay").randint(
                    minimum, maximum
                )
            )
        canonical = event.model_copy(update={"produced_at": event.occurred_at + delay})
        events.append(canonical)
        ordinal = len(scheduled)
        scheduled.append((canonical.produced_at, ordinal, 1, canonical))
        if (
            random.stream(f"{name}:duplicate-selection").random()
            < traffic.duplicate_delivery_probability
        ):
            scheduled.append(
                (
                    canonical.produced_at + traffic.duplicate_delivery_delay,
                    ordinal,
                    2,
                    canonical,
                )
            )
    deliveries = tuple(
        DeliveryRecord(sequence, at, attempt, event)
        for sequence, (at, _, attempt, event) in enumerate(
            sorted(scheduled, key=lambda item: (item[0], item[1], item[2])), 1
        )
    )
    canonical_events = tuple(events)
    return MixedWorkloadResult(
        manifest=legitimate.manifest,
        world_config=world,
        traffic_config=traffic,
        legitimate=legitimate,
        fraud=fraud,
        users=legitimate.users + fraud.users,
        devices=legitimate.devices + fraud.devices,
        transactions=legitimate.transactions + fraud.transactions,
        payment_attempts=legitimate.payment_attempts + fraud.payment_attempts,
        canonical_events=canonical_events,
        delivery_records=deliveries,
        traffic_summary=_summary(canonical_events, deliveries),
    )
