"""Readable synthetic identities allocated independently by kind."""

import re

_KIND = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


class IdentityAllocator:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, kind: str) -> str:
        if not isinstance(kind, str) or _KIND.fullmatch(kind) is None:
            raise ValueError("identity kind must be a lowercase machine code")
        number = self._counters.get(kind, 0) + 1
        self._counters[kind] = number
        return f"{kind}-{number:06d}"
