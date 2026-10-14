"""Deterministic, separated workload artifact bundle."""

import hashlib
import json
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from argus.events.kafka import deserialize_fraud_event, serialize_fraud_event
from argus.simulation.kernel import SIMULATOR_VERSION
from argus.simulation.spec import WorkloadSpec
from argus.simulation.workload import MixedWorkloadResult

BUNDLE_FORMAT_VERSION = 1
_FILES = (
    "metadata.json",
    "production/users.jsonl",
    "production/devices.jsonl",
    "production/transactions.jsonl",
    "production/payment-attempts.jsonl",
    "events/canonical-events.jsonl",
    "transport/delivery-schedule.jsonl",
    "truth/fraud-rings.jsonl",
    "truth/card-uses.jsonl",
    "truth/promo-redemptions.jsonl",
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _write_lines(root: Path, name: str, rows: list[object]) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes("".join(_canonical(row) + "\n" for row in rows).encode("utf-8"))


def _truth_row(value: object) -> dict:
    result = asdict(value)
    for key, item in result.items():
        if isinstance(item, datetime):
            result[key] = _utc(item)
    return result


def export_workload(result: MixedWorkloadResult, output_directory: str | Path) -> Path:
    """Write to a staging sibling, then install only at a nonexisting destination."""
    destination = Path(output_directory)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}-", dir=destination.parent
    ) as temporary:
        root = Path(temporary) / "bundle"
        root.mkdir()
        spec = WorkloadSpec(
            simulation=result_to_config(result),
            world=result.world_config,
            traffic=result.traffic_config,
        )
        summary = result.traffic_summary
        counts = {
            "users": len(result.users),
            "devices": len(result.devices),
            "transactions": len(result.transactions),
            "payment_attempts": len(result.payment_attempts),
            "fraud_rings": len(result.fraud.ring_truth),
            "card_uses": len(result.fraud.card_uses),
            "promo_redemptions": len(result.fraud.promo_redemptions),
            "logical_event_count": summary.logical_event_count,
            "delivery_count": summary.delivery_count,
            "duplicate_delivery_count": summary.duplicate_delivery_count,
            "late_logical_event_count": summary.late_logical_event_count,
        }
        (root / "metadata.json").write_bytes(
            (
                _canonical(
                    {
                        "bundle_format_version": BUNDLE_FORMAT_VERSION,
                        "simulator_version": SIMULATOR_VERSION,
                        "manifest": json.loads(result.manifest.to_json()),
                        "workload_spec": json.loads(spec.to_json()),
                        "counts": counts,
                    }
                )
                + "\n"
            ).encode("utf-8")
        )
        for name, values in (
            ("users", result.users),
            ("devices", result.devices),
            ("transactions", result.transactions),
            ("payment-attempts", result.payment_attempts),
        ):
            _write_lines(
                root,
                f"production/{name}.jsonl",
                [json.loads(value.model_dump_json()) for value in values],
            )
        event_path = root / "events/canonical-events.jsonl"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event_path.write_bytes(
            b"".join(
                serialize_fraud_event(event) + b"\n"
                for event in result.canonical_events
            )
        )
        _write_lines(
            root,
            "transport/delivery-schedule.jsonl",
            [
                {
                    "sequence": delivery.sequence,
                    "deliver_at": _utc(delivery.deliver_at),
                    "attempt": delivery.attempt,
                    "event_id": str(delivery.event.event_id),
                }
                for delivery in result.delivery_records
            ],
        )
        for name, values in (
            ("fraud-rings", result.fraud.ring_truth),
            ("card-uses", result.fraud.card_uses),
            ("promo-redemptions", result.fraud.promo_redemptions),
        ):
            _write_lines(
                root, f"truth/{name}.jsonl", [_truth_row(value) for value in values]
            )
        checksums = "".join(
            f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\n"
            for name in sorted(_FILES)
        )
        (root / "checksums.sha256").write_text(checksums, encoding="utf-8")
        verify_bundle(root)
        root.rename(destination)
    return destination


def result_to_config(result: MixedWorkloadResult):
    from argus.simulation.config import SimulationConfig

    return SimulationConfig(
        seed=result.manifest.seed, starts_at=result.manifest.starts_at
    )


@dataclass(frozen=True, slots=True)
class BundleVerification:
    logical_event_count: int
    delivery_count: int


def verify_bundle(path: str | Path) -> BundleVerification:
    root = Path(path)
    if {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} != set(
        _FILES
    ) | {"checksums.sha256"}:
        raise ValueError("bundle file set mismatch")
    expected = "".join(
        f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\n"
        for name in sorted(_FILES)
    )
    if (root / "checksums.sha256").read_text(encoding="utf-8") != expected:
        raise ValueError("bundle checksum mismatch")
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    if (
        metadata["bundle_format_version"] != BUNDLE_FORMAT_VERSION
        or metadata["simulator_version"] != SIMULATOR_VERSION
    ):
        raise ValueError("unsupported bundle or simulator version")
    spec = WorkloadSpec.from_json(_canonical(metadata["workload_spec"]))
    if json.loads(spec.to_json()) != metadata["workload_spec"]:
        raise ValueError("noncanonical spec")
    if (
        metadata["manifest"]["seed"] != spec.simulation.seed
        or metadata["manifest"]["starts_at"] != _utc(spec.simulation.starts_at)
        or metadata["manifest"]["simulator_version"] != SIMULATOR_VERSION
    ):
        raise ValueError("manifest and spec mismatch")

    def rows(name: str) -> list[dict]:
        return [
            json.loads(line)
            for line in (root / name).read_text(encoding="utf-8").splitlines()
        ]

    counts = metadata["counts"]
    for name, key in (
        ("production/users.jsonl", "users"),
        ("production/devices.jsonl", "devices"),
        ("production/transactions.jsonl", "transactions"),
        ("production/payment-attempts.jsonl", "payment_attempts"),
        ("truth/fraud-rings.jsonl", "fraud_rings"),
        ("truth/card-uses.jsonl", "card_uses"),
        ("truth/promo-redemptions.jsonl", "promo_redemptions"),
    ):
        if len(rows(name)) != counts[key]:
            raise ValueError(f"{name} count mismatch")
    events = [
        deserialize_fraud_event(line)
        for line in (root / "events/canonical-events.jsonl").read_bytes().splitlines()
    ]
    ids = {str(event.event_id) for event in events}
    if len(events) != counts["logical_event_count"] or len(ids) != len(events):
        raise ValueError("canonical event count or identity mismatch")
    if (
        sum(event.produced_at > event.occurred_at for event in events)
        != counts["late_logical_event_count"]
    ):
        raise ValueError("late event count mismatch")
    schedule = rows("transport/delivery-schedule.jsonl")
    if len(schedule) != counts["delivery_count"]:
        raise ValueError("delivery count mismatch")
    attempts = Counter((row["event_id"], row["attempt"]) for row in schedule)
    if any(
        row["sequence"] != index
        or row["event_id"] not in ids
        or row["attempt"] not in (1, 2)
        for index, row in enumerate(schedule, 1)
    ):
        raise ValueError("invalid delivery reference or sequence")
    by_id = {str(event.event_id): event for event in events}
    if any(
        datetime.fromisoformat(row["deliver_at"].replace("Z", "+00:00"))
        < by_id[row["event_id"]].produced_at
        for row in schedule
    ):
        raise ValueError("delivery precedes production")
    if any(
        datetime.fromisoformat(schedule[index]["deliver_at"].replace("Z", "+00:00"))
        < datetime.fromisoformat(
            schedule[index - 1]["deliver_at"].replace("Z", "+00:00")
        )
        for index in range(1, len(schedule))
    ):
        raise ValueError("delivery schedule out of order")
    if any(
        attempts[(event_id, 1)] != 1 or attempts[(event_id, 2)] > 1 for event_id in ids
    ):
        raise ValueError("invalid delivery attempts")
    if (
        sum(attempt == 2 for _, attempt in attempts)
        != counts["duplicate_delivery_count"]
    ):
        raise ValueError("duplicate count mismatch")
    users = {row["user_id"] for row in rows("production/users.jsonl")}
    devices = {row["device_id"] for row in rows("production/devices.jsonl")}
    transactions = {
        row["transaction_id"]: row["user_id"]
        for row in rows("production/transactions.jsonl")
    }
    ring_rows = rows("truth/fraud-rings.jsonl")
    rings = {row["ring_id"]: row for row in ring_rows}
    for row in ring_rows:
        if (
            not set(row["member_user_ids"]) <= users
            or row["shared_device_id"] not in devices
        ):
            raise ValueError("orphan fraud ring relationship")
    for name in ("card-uses", "promo-redemptions"):
        for row in rows(f"truth/{name}.jsonl"):
            if (
                row["ring_id"] not in rings
                or row["user_id"] not in users
                or transactions.get(row["transaction_id"]) != row["user_id"]
            ):
                raise ValueError("orphan truth relationship")
            ring = rings[row["ring_id"]]
            if row["user_id"] not in ring["member_user_ids"]:
                raise ValueError("truth user is outside ring")
            if name == "card-uses" and row["card_id"] != ring["shared_card_id"]:
                raise ValueError("truth card does not match ring")
            if (
                name == "promo-redemptions"
                and row["promo_code"] != ring["shared_promo_code"]
            ):
                raise ValueError("truth promo does not match ring")
    return BundleVerification(len(events), len(schedule))
