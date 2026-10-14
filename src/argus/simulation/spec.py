"""Typed, canonical reconstruction of a mixed workload."""

import json
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from typing import Any

from argus.simulation.config import SimulationConfig
from argus.simulation.fraud_world import FraudScenarioConfig
from argus.simulation.legitimate import LegitimateScenarioConfig
from argus.simulation.workload import MixedWorldConfig, TrafficBehaviorConfig


def _parse_config(cls: type, data: object) -> Any:
    if not isinstance(data, dict):
        raise ValueError(f"{cls.__name__} must be an object")
    duration_names = {field.name for field in fields(cls) if field.type is timedelta}
    expected = {
        f"{name}_us" if name in duration_names else name
        for name in (field.name for field in fields(cls))
    }
    if set(data) != expected:
        raise ValueError(f"{cls.__name__} fields mismatch")
    values = {}
    for field in fields(cls):
        if field.name in duration_names:
            value = data[f"{field.name}_us"]
            if type(value) is not int:
                raise ValueError(f"{field.name}_us must be an integer")
            values[field.name] = timedelta(microseconds=value)
        else:
            values[field.name] = data[field.name]
    return cls(**values)


@dataclass(frozen=True, slots=True)
class WorkloadSpec:
    simulation: SimulationConfig
    world: MixedWorldConfig
    traffic: TrafficBehaviorConfig

    def __post_init__(self) -> None:
        if not isinstance(self.simulation, SimulationConfig):
            raise TypeError("simulation must be SimulationConfig")
        if not isinstance(self.world, MixedWorldConfig):
            raise TypeError("world must be MixedWorldConfig")
        if not isinstance(self.traffic, TrafficBehaviorConfig):
            raise TypeError("traffic must be TrafficBehaviorConfig")

    def to_json(self) -> str:
        return json.dumps(
            {
                "simulation": {
                    "seed": self.simulation.seed,
                    "starts_at": self.simulation.starts_at.isoformat().replace(
                        "+00:00", "Z"
                    ),
                },
                "world": json.loads(self.world.to_json()),
                "traffic": json.loads(self.traffic.to_json()),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, source: str | bytes) -> "WorkloadSpec":
        data = json.loads(source)
        if not isinstance(data, dict) or set(data) != {
            "simulation",
            "world",
            "traffic",
        }:
            raise ValueError("workload spec fields mismatch")
        simulation = data["simulation"]
        world = data["world"]
        if not isinstance(simulation, dict) or set(simulation) != {"seed", "starts_at"}:
            raise ValueError("simulation fields mismatch")
        if not isinstance(world, dict) or set(world) != {
            "fraud",
            "identity_strategy",
            "legitimate",
        }:
            raise ValueError("world fields mismatch")
        if world["identity_strategy"] != "sha256-opaque-scope-v1":
            raise ValueError("unsupported identity strategy")
        if type(simulation["starts_at"]) is not str:
            raise ValueError("starts_at must be ISO-8601 text")
        return cls(
            simulation=SimulationConfig(
                seed=simulation["seed"],
                starts_at=datetime.fromisoformat(
                    simulation["starts_at"].replace("Z", "+00:00")
                ),
            ),
            world=MixedWorldConfig(
                legitimate=_parse_config(LegitimateScenarioConfig, world["legitimate"]),
                fraud=_parse_config(FraudScenarioConfig, world["fraud"]),
            ),
            traffic=_parse_config(TrafficBehaviorConfig, data["traffic"]),
        )
