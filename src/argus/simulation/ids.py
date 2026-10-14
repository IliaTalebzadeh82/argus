"""Readable synthetic identities allocated independently by kind."""

import re

_KIND = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")


class IdentityAllocator:
    def __init__(self, scope: str | None = None) -> None:
        if scope is not None and re.fullmatch(r"[0-9a-f]{12}", scope) is None:
            raise ValueError("scope must be twelve lowercase hexadecimal digits")
        self._scope = scope
        self._counters: dict[str, int] = {}

    def next(self, kind: str) -> str:
        if not isinstance(kind, str) or _KIND.fullmatch(kind) is None:
            raise ValueError("identity kind must be a lowercase machine code")
        number = self._counters.get(kind, 0) + 1
        self._counters[kind] = number
        if self._scope is None:
            return f"{kind}-{number:06d}"
        return f"{kind}-{self._scope}-{number:06d}"
