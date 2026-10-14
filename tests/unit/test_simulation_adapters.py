"""Offline CP05 specification, bundle, and playback contracts."""

import json
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from argus.events.kafka import deserialize_fraud_event, serialize_fraud_event
from argus.simulation.export import export_workload, verify_bundle
from argus.simulation.playback import play_workload
from argus.simulation.spec import WorkloadSpec
from argus.simulation.workload import DeliveryRecord, run_mixed_workload

SPEC = Path("configs/simulation/phase-03-demo.json")


def workload(spec: WorkloadSpec | None = None):
    spec = spec or WorkloadSpec.from_json(SPEC.read_text(encoding="utf-8"))
    return run_mixed_workload(spec.simulation, spec.world, spec.traffic)


def test_checked_in_spec_round_trip_and_determinism():
    spec = WorkloadSpec.from_json(SPEC.read_text(encoding="utf-8"))
    assert WorkloadSpec.from_json(spec.to_json()) == spec
    assert spec.to_json() + "\n" == SPEC.read_text(encoding="utf-8")
    assert workload(spec) == workload(WorkloadSpec.from_json(spec.to_json()))
    assert workload(
        replace(spec, simulation=replace(spec.simulation, seed=18))
    ) != workload(spec)


def test_bundle_bytes_separation_and_references(tmp_path):
    result = workload()
    left, right = tmp_path / "left", tmp_path / "right"
    export_workload(result, left)
    export_workload(workload(), right)
    files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    assert files == sorted(
        path.relative_to(right) for path in right.rglob("*") if path.is_file()
    )
    assert all(
        (left / path).read_bytes() == (right / path).read_bytes() for path in files
    )
    assert verify_bundle(left).logical_event_count == len(result.canonical_events)
    assert verify_bundle(left).delivery_count == len(result.delivery_records)
    with pytest.raises(FileExistsError):
        export_workload(result, left)
    for area in ("production", "events", "transport"):
        for file in (left / area).glob("*.jsonl"):
            for line in file.read_text().splitlines():
                assert not (
                    {
                        "ring_id",
                        "shared_card_id",
                        "shared_promo_code",
                        "promo_code",
                        "ground_truth",
                        "is_fraud",
                    }
                    & set(json.loads(line))
                )
    event_lines = (left / "events/canonical-events.jsonl").read_bytes().splitlines()
    assert (
        tuple(deserialize_fraud_event(line) for line in event_lines)
        == result.canonical_events
    )
    assert event_lines == [
        serialize_fraud_event(event) for event in result.canonical_events
    ]
    schedule = [
        json.loads(line)
        for line in (left / "transport/delivery-schedule.jsonl")
        .read_text()
        .splitlines()
    ]
    assert {row["event_id"] for row in schedule} == {
        str(event.event_id) for event in result.canonical_events
    }
    assert (
        Counter(row["attempt"] for row in schedule)[2]
        == result.traffic_summary.duplicate_delivery_count
    )
    other = tmp_path / "other"
    spec = WorkloadSpec.from_json(SPEC.read_text())
    export_workload(
        workload(replace(spec, simulation=replace(spec.simulation, seed=18))), other
    )
    assert (other / "checksums.sha256").read_bytes() != (
        left / "checksums.sha256"
    ).read_bytes()


def test_bundle_rejects_corruption(tmp_path):
    root = tmp_path / "bundle"
    export_workload(workload(), root)
    file = root / "truth/card-uses.jsonl"
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum"):
        verify_bundle(root)


def test_unpaced_order_duplicate_and_failure():
    result = workload()
    calls = []

    class Recording:
        def publish(self, event):
            calls.append(event)

    report = play_workload(
        result, Recording(), sleep=lambda _: pytest.fail("unpaced slept")
    )
    assert report.published_deliveries == len(result.delivery_records)
    assert calls == [record.event for record in result.delivery_records]
    assert len({id(event) for event in calls}) == len(result.canonical_events)

    class Failing:
        def publish(self, event):
            calls.append(event)
            if len(calls) == 4:
                raise RuntimeError("publish failed")

    calls.clear()
    with pytest.raises(RuntimeError, match="publish failed"):
        play_workload(result, Failing())
    assert calls == [record.event for record in result.delivery_records[:4]]


def test_pacing_uses_absolute_monotonic_targets():
    result = workload()
    first = result.delivery_records[0]
    records = tuple(
        DeliveryRecord(
            index,
            first.deliver_at + timedelta(seconds=10 * (index - 1)),
            1,
            first.event,
        )
        for index in range(1, 4)
    )
    result = replace(result, delivery_records=records)
    now = [0.0]
    sleeps = []
    publish_times = []

    class Publisher:
        def __init__(self, latency):
            self.latency = latency

        def publish(self, event):
            publish_times.append(now[0])
            now[0] += self.latency

    def fake_sleep(duration):
        assert duration > 0
        sleeps.append(duration)
        now[0] += duration

    play_workload(
        result,
        Publisher(2),
        speedup=2,
        monotonic=lambda: now[0],
        sleep=fake_sleep,
    )
    assert publish_times == [0, 5, 10]
    assert sleeps == [3, 3]

    now[0] = 0
    sleeps.clear()
    publish_times.clear()
    play_workload(
        result,
        Publisher(6),
        speedup=2,
        monotonic=lambda: now[0],
        sleep=fake_sleep,
    )
    assert publish_times == [0, 6, 12]
    assert sleeps == []
    for bad in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            play_workload(result, Publisher(0), speedup=bad)
