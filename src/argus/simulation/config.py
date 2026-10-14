"""Immutable inputs to one simulation run."""

from dataclasses import dataclass
from datetime import UTC, datetime


def normalize_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("starts_at must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("starts_at must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    seed: int
    starts_at: datetime

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be an integer, not bool")
        object.__setattr__(self, "starts_at", normalize_utc(self.starts_at))
