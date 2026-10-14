"""Sequential Kafka-compatible playback of a pure delivery schedule."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from argus.events.envelope import EventEnvelope
from argus.events.fraud import FraudPayload
from argus.simulation.workload import MixedWorkloadResult


class FraudEventPublisher(Protocol):
    def publish(self, event: EventEnvelope[FraudPayload]) -> None: ...


@dataclass(frozen=True, slots=True)
class PlaybackReport:
    scheduled_deliveries: int
    published_deliveries: int
    first_sequence: int | None
    last_sequence: int | None
    mode: str
    speedup: float | None


def play_workload(
    result: MixedWorkloadResult,
    publisher: FraudEventPublisher,
    *,
    speedup: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> PlaybackReport:
    if speedup is not None and (
        type(speedup) not in (int, float) or not math.isfinite(speedup) or speedup <= 0
    ):
        raise ValueError("speedup must be positive and finite")
    deliveries = result.delivery_records
    if any(delivery.sequence != index for index, delivery in enumerate(deliveries, 1)):
        raise ValueError("delivery sequence must be consecutive from 1")
    start = monotonic() if speedup is not None and deliveries else 0.0
    first = deliveries[0].deliver_at if deliveries else None
    for delivery in deliveries:
        if speedup is not None and first is not None:
            target = (delivery.deliver_at - first).total_seconds() / speedup
            remaining = target - (monotonic() - start)
            if remaining > 0:
                sleep(remaining)
        publisher.publish(delivery.event)
    return PlaybackReport(
        scheduled_deliveries=len(deliveries),
        published_deliveries=len(deliveries),
        first_sequence=deliveries[0].sequence if deliveries else None,
        last_sequence=deliveries[-1].sequence if deliveries else None,
        mode="paced" if speedup is not None else "unpaced",
        speedup=float(speedup) if speedup is not None else None,
    )
