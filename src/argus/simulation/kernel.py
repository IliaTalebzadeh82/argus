"""Stateful deterministic kernel and immutable output metadata."""

import json
from dataclasses import dataclass
from datetime import datetime

from argus.simulation.clock import SimulationClock
from argus.simulation.config import SimulationConfig, normalize_utc
from argus.simulation.ids import IdentityAllocator
from argus.simulation.random import SimulationRandom

SIMULATOR_VERSION = 1


@dataclass(frozen=True, slots=True)
class SimulationManifest:
    seed: int
    starts_at: datetime
    simulator_version: int

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be an integer, not bool")
        if type(self.simulator_version) is not int or self.simulator_version < 1:
            raise ValueError("simulator_version must be a positive integer")
        object.__setattr__(self, "starts_at", normalize_utc(self.starts_at))

    def to_json(self) -> str:
        return json.dumps(
            {
                "seed": self.seed,
                "simulator_version": self.simulator_version,
                "starts_at": self.starts_at.isoformat().replace("+00:00", "Z"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class SimulationRecord[T]:
    sequence: int
    generated_at: datetime
    value: T


class SimulationKernel:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.random = SimulationRandom(config.seed)
        self.clock = SimulationClock(config.starts_at)
        self.ids = IdentityAllocator()
        self._sequence = 0

    @property
    def manifest(self) -> SimulationManifest:
        return SimulationManifest(
            seed=self.config.seed,
            starts_at=self.config.starts_at,
            simulator_version=SIMULATOR_VERSION,
        )

    def emit[T](self, value: T) -> SimulationRecord[T]:
        self._sequence += 1
        return SimulationRecord(
            sequence=self._sequence,
            generated_at=self.clock.now(),
            value=value,
        )
