"""Clock advanced solely by simulation code."""

from datetime import datetime, timedelta

from argus.simulation.config import normalize_utc


class SimulationClock:
    def __init__(self, starts_at: datetime) -> None:
        self._current = normalize_utc(starts_at)

    def now(self) -> datetime:
        return self._current

    def advance(self, duration: timedelta) -> datetime:
        if not isinstance(duration, timedelta):
            raise TypeError("duration must be a timedelta")
        if duration < timedelta(0):
            raise ValueError("simulation clock cannot rewind")
        self._current += duration
        return self._current
