"""Offline contract tests for the deterministic simulation foundation."""

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest

from argus.simulation import (
    IdentityAllocator,
    SimulationClock,
    SimulationConfig,
    SimulationKernel,
    SimulationManifest,
    SimulationRandom,
)

START = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)


def toy_kernel_fixture(kernel: SimulationKernel) -> list:
    """Exercise the primitives; this is not a synthetic user behavior model."""
    kernel.clock.advance(timedelta(minutes=2))
    return [
        kernel.emit(
            (kernel.ids.next("user"), kernel.random.stream("users").getrandbits(64))
        )
        for _ in range(3)
    ]


def test_config_requires_integer_seed_and_aware_start() -> None:
    offset = timezone(timedelta(hours=3, minutes=30))
    config = SimulationConfig(0, datetime(2026, 1, 2, 6, 34, tzinfo=offset))
    assert config.starts_at == START
    assert config.starts_at.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        config.seed = 1
    for seed in (True, 1.0, "1", None):
        with pytest.raises(TypeError):
            SimulationConfig(seed, START)
    with pytest.raises(ValueError, match="timezone-aware"):
        SimulationConfig(1, START.replace(tzinfo=None))


def test_named_streams_are_persistent_reproducible_and_local() -> None:
    first = SimulationRandom(17)
    users = first.stream("users:user-000001")
    expected = [users.getrandbits(64) for _ in range(3)]
    assert first.stream("users:user-000001") is users
    second = SimulationRandom(17)
    assert [
        second.stream("users:user-000001").getrandbits(64) for _ in range(3)
    ] == expected
    assert users.getrandbits(64) == second.stream("users:user-000001").getrandbits(64)
    assert [first.stream("payments").getrandbits(64) for _ in range(3)] != expected
    isolated = SimulationRandom(17)
    for _ in range(100):
        isolated.stream("promo").getrandbits(64)
    isolated.stream("unrelated")
    fresh = SimulationRandom(17)
    assert [isolated.stream("payments").getrandbits(64) for _ in range(3)] == [
        fresh.stream("payments").getrandbits(64) for _ in range(3)
    ]


def test_random_source_rejects_invalid_inputs() -> None:
    with pytest.raises(TypeError):
        SimulationRandom(True)
    random = SimulationRandom(1)
    for namespace in ("", " ", "../users", "Users", "users::one", "users--one"):
        with pytest.raises(ValueError):
            random.stream(namespace)


def test_clock_only_advances_explicitly() -> None:
    clock = SimulationClock(START)
    assert clock.now() == START
    assert clock.advance(timedelta(0)) == START
    assert clock.advance(timedelta(seconds=5)) == START + timedelta(seconds=5)
    assert clock.now() == START + timedelta(seconds=5)
    with pytest.raises(ValueError, match="rewind"):
        clock.advance(timedelta(microseconds=-1))
    with pytest.raises(TypeError):
        clock.advance(1)


def test_identity_allocation_and_invalid_kinds() -> None:
    one, two = IdentityAllocator(), IdentityAllocator()
    order = ("user", "device", "user", "payment", "user")
    expected = [
        "user-000001",
        "device-000001",
        "user-000002",
        "payment-000001",
        "user-000003",
    ]
    assert [one.next(kind) for kind in order] == expected
    assert [two.next(kind) for kind in order] == expected
    for kind in ("", " ", "../../user", "User", "bad_kind", "bad--kind"):
        with pytest.raises(ValueError):
            one.next(kind)


def test_manifest_is_immutable_and_canonical() -> None:
    manifest = SimulationKernel(SimulationConfig(-5, START)).manifest
    assert manifest == SimulationManifest(-5, START, 1)
    assert (
        manifest.to_json()
        == '{"seed":-5,"simulator_version":1,"starts_at":"2026-01-02T03:04:00Z"}'
    )
    assert json.loads(manifest.to_json())["starts_at"].endswith("Z")
    with pytest.raises(FrozenInstanceError):
        manifest.simulator_version = 2
    for invalid in (0, -1, True, "1"):
        with pytest.raises(ValueError):
            SimulationManifest(1, START, invalid)


def test_kernel_reproduces_records_and_sequence() -> None:
    config = SimulationConfig(123, START)
    first, second = SimulationKernel(config), SimulationKernel(config)
    records = toy_kernel_fixture(first)
    assert records == toy_kernel_fixture(second)
    assert first.manifest == second.manifest
    assert [record.sequence for record in records] == [1, 2, 3]
    assert [record.value[0] for record in records] == [
        "user-000001",
        "user-000002",
        "user-000003",
    ]
    assert all(
        record.generated_at == START + timedelta(minutes=2) for record in records
    )
    with pytest.raises(FrozenInstanceError):
        records[0].sequence = 8


def test_seed_and_start_time_are_separate_dimensions() -> None:
    baseline = toy_kernel_fixture(SimulationKernel(SimulationConfig(123, START)))
    different_seed = toy_kernel_fixture(SimulationKernel(SimulationConfig(124, START)))
    different_time = toy_kernel_fixture(
        SimulationKernel(SimulationConfig(123, START + timedelta(days=1)))
    )
    assert [r.value[0] for r in baseline] == [r.value[0] for r in different_seed]
    assert [r.value[1] for r in baseline] != [r.value[1] for r in different_seed]
    assert [r.value for r in baseline] == [r.value for r in different_time]
    assert [r.generated_at for r in baseline] != [
        r.generated_at for r in different_time
    ]
