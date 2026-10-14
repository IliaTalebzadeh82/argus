"""Simulator-owned, persistent named PRNG streams."""

import hashlib
import random
import re

_SEGMENT = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
_NAMESPACE = re.compile(rf"{_SEGMENT}(?::{_SEGMENT})*")


class SimulationRandom:
    """Each name owns one stateful stream; repeated lookup continues that stream."""

    def __init__(self, seed: int) -> None:
        if type(seed) is not int:
            raise TypeError("seed must be an integer, not bool")
        self._seed = seed
        self._streams: dict[str, random.Random] = {}

    def stream(self, namespace: str) -> random.Random:
        if not isinstance(namespace, str) or _NAMESPACE.fullmatch(namespace) is None:
            raise ValueError(
                "namespace must be lowercase machine codes separated by ':'"
            )
        if namespace not in self._streams:
            material = f"{self._seed}:{namespace}".encode()
            derived_seed = int.from_bytes(hashlib.sha256(material).digest())
            self._streams[namespace] = random.Random(derived_seed)
        return self._streams[namespace]
