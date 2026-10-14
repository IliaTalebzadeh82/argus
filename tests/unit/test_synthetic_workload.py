"""Mixed population, event time, and at-least-once transport contracts."""

from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from argus.events.features import ApplyResult, ReferenceFeatureProjector
from argus.events.fraud import validate_fraud_event
from argus.simulation.config import SimulationConfig
from argus.simulation.fraud_world import FraudScenarioConfig
from argus.simulation.legitimate import LegitimateScenarioConfig
from argus.simulation.workload import (
    MixedWorldConfig,
    TrafficBehaviorConfig,
    run_mixed_workload,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def world() -> MixedWorldConfig:
    return MixedWorldConfig(
        legitimate=LegitimateScenarioConfig(
            user_count=3,
            payments_per_user=3,
            merchant_count=4,
            payment_failure_probability=0.5,
            min_amount_minor=100,
            max_amount_minor=1000,
            currency="USD",
            account_spacing=timedelta(minutes=10),
            first_payment_delay=timedelta(minutes=2),
            payment_spacing=timedelta(minutes=3),
            terminal_delay=timedelta(seconds=1),
        ),
        fraud=FraudScenarioConfig(
            ring_count=1,
            accounts_per_ring=4,
            payments_per_account=3,
            merchant_count=4,
            payment_failure_probability=1,
            chargeback_probability=0,
            min_amount_minor=100,
            max_amount_minor=1000,
            currency="USD",
            ring_spacing=timedelta(hours=1),
            account_spacing=timedelta(seconds=1),
            first_payment_delay=timedelta(seconds=2),
            payment_spacing=timedelta(seconds=2),
            terminal_delay=timedelta(seconds=1),
            chargeback_delay=timedelta(days=1),
        ),
    )


def traffic(**changes: object) -> TrafficBehaviorConfig:
    values = dict(
        late_event_probability=0.5,
        min_production_delay=timedelta(seconds=1),
        max_production_delay=timedelta(minutes=12),
        duplicate_delivery_probability=0.5,
        duplicate_delivery_delay=timedelta(seconds=2),
    )
    return TrafficBehaviorConfig(**(values | changes))


def run(
    config: MixedWorldConfig | None = None,
    behavior: TrafficBehaviorConfig | None = None,
    seed: int = 17,
):
    return run_mixed_workload(
        SimulationConfig(seed=seed, starts_at=START),
        config or world(),
        behavior or traffic(),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("late_event_probability", True),
        ("late_event_probability", -0.1),
        ("late_event_probability", 1.1),
        ("late_event_probability", float("nan")),
        ("late_event_probability", float("inf")),
        ("duplicate_delivery_probability", False),
        ("duplicate_delivery_probability", float("-inf")),
        ("min_production_delay", timedelta(seconds=-1)),
        ("min_production_delay", 0),
        ("max_production_delay", timedelta(seconds=-1)),
        ("duplicate_delivery_delay", timedelta(seconds=-1)),
    ],
)
def test_invalid_traffic(field, value):
    with pytest.raises((TypeError, ValueError)):
        traffic(**{field: value})


def test_reversed_delay_and_mixed_config_validation():
    with pytest.raises(ValueError):
        traffic(min_production_delay=timedelta(minutes=13))
    with pytest.raises(TypeError):
        MixedWorldConfig(legitimate=None, fraud=world().fraud)
    with pytest.raises(TypeError):
        MixedWorldConfig(legitimate=world().legitimate, fraud=None)
    assert '"identity_strategy"' in world().to_json()
    assert '"duplicate_delivery_delay_us"' in traffic().to_json()


def test_identity_references_and_truth_boundary():
    result = run()
    user_ids = [user.user_id for user in result.users]
    device_ids = [device.device_id for device in result.devices]
    transaction_ids = [tx.transaction_id for tx in result.transactions]
    payment_ids = [attempt.payment_id for attempt in result.payment_attempts]
    event_ids = [event.event_id for event in result.canonical_events]
    assert len(result.users) == 7
    assert len(result.devices) == 4
    for ids in (user_ids, device_ids, transaction_ids, payment_ids, event_ids):
        assert len(ids) == len(set(ids))
    assert set(user.user_id for user in result.legitimate.users).isdisjoint(
        user.user_id for user in result.fraud.users
    )
    assert set(device.device_id for device in result.legitimate.devices).isdisjoint(
        device.device_id for device in result.fraud.devices
    )
    assert all(tx.user_id in user_ids for tx in result.transactions)
    assert all(
        attempt.transaction_id in transaction_ids for attempt in result.payment_attempts
    )
    assert all(
        use.user_id in user_ids and use.transaction_id in transaction_ids
        for use in result.fraud.card_uses
    )
    assert all(
        p.user_id in user_ids and p.transaction_id in transaction_ids
        for p in result.fraud.promo_redemptions
    )
    for ring in result.fraud.ring_truth:
        assert set(ring.member_user_ids) <= set(user_ids)
        assert ring.shared_device_id in device_ids
    production_ids = user_ids + device_ids + transaction_ids + payment_ids
    assert not any(
        marker in identifier
        for identifier in production_ids
        for marker in ("fraud", "legit", "normal", "ring", "criminal")
    )
    for event in result.canonical_events:
        validate_fraud_event(event)
        assert event.subject_id in set(user_ids + transaction_ids + payment_ids)
        for value in event.payload.model_dump().values():
            if value is not None:
                assert value in set(
                    user_ids + device_ids + transaction_ids + payment_ids
                )
        assert not any(
            marker in event.model_dump_json()
            for marker in ("ground_truth", "ring_id", "card_id", "promo_code")
        )


def test_chargeback_identity_and_references():
    config = replace(
        world(),
        fraud=replace(
            world().fraud,
            payment_failure_probability=0,
            chargeback_probability=1,
        ),
    )
    result = run(config)
    chargebacks = [
        e for e in result.canonical_events if e.event_type == "chargeback.received"
    ]
    assert len(chargebacks) == 12
    assert len({e.payload.chargeback_id for e in chargebacks}) == 12
    assert len({e.event_id for e in result.canonical_events}) == len(
        result.canonical_events
    )
    assert all(
        e.payload.transaction_id in {tx.transaction_id for tx in result.transactions}
        for e in chargebacks
    )
    assert all(
        e.payload.user_id in {user.user_id for user in result.users}
        for e in chargebacks
    )
    assert all("fraud" not in e.payload.chargeback_id for e in chargebacks)


def test_reproduction_seed_and_composition_locality():
    baseline = run()
    assert baseline == run()
    assert baseline.metadata_json() == run().metadata_json()
    other_seed = run(seed=18)
    assert baseline.transactions != other_seed.transactions
    assert baseline.delivery_records != other_seed.delivery_records
    more_rings = run(replace(world(), fraud=replace(world().fraud, ring_count=2)))
    assert baseline.legitimate.users == more_rings.legitimate.users
    assert baseline.legitimate.transactions == more_rings.legitimate.transactions
    assert baseline.legitimate.event_records == more_rings.legitimate.event_records
    more_users = run(
        replace(world(), legitimate=replace(world().legitimate, user_count=4))
    )
    assert baseline.fraud.transactions == more_users.fraud.transactions
    assert baseline.fraud.ring_truth == more_users.fraud.ring_truth


def test_transport_boundaries_and_exact_duplicates():
    zero = run(
        behavior=traffic(late_event_probability=0, duplicate_delivery_probability=0)
    )
    assert len(zero.delivery_records) == len(zero.canonical_events)
    assert all(e.produced_at == e.occurred_at for e in zero.canonical_events)
    full = run(
        behavior=traffic(
            late_event_probability=1,
            min_production_delay=timedelta(seconds=1),
            max_production_delay=timedelta(seconds=1),
            duplicate_delivery_probability=1,
            duplicate_delivery_delay=timedelta(0),
        )
    )
    assert len(full.delivery_records) == 2 * len(full.canonical_events)
    assert all(
        e.produced_at - e.occurred_at == timedelta(seconds=1)
        for e in full.canonical_events
    )
    assert [d.sequence for d in full.delivery_records] == list(
        range(1, len(full.delivery_records) + 1)
    )
    by_event = {}
    for delivery in full.delivery_records:
        by_event.setdefault(delivery.event.event_id, []).append(delivery)
    for attempts in by_event.values():
        assert [d.attempt for d in attempts] == [1, 2]
        assert attempts[0].event is attempts[1].event
        assert attempts[0].deliver_at == attempts[1].deliver_at


def test_traffic_independence_and_event_locality():
    baseline = run()
    no_dupes = run(behavior=replace(traffic(), duplicate_delivery_probability=0))
    later_dupes = run(
        behavior=replace(traffic(), duplicate_delivery_delay=timedelta(minutes=5))
    )
    assert baseline.legitimate == no_dupes.legitimate
    assert baseline.fraud == no_dupes.fraud
    assert baseline.canonical_events == no_dupes.canonical_events
    assert baseline.canonical_events == later_dupes.canonical_events
    no_late = run(behavior=replace(traffic(), late_event_probability=0))
    assert baseline.legitimate == no_late.legitimate
    assert baseline.fraud == no_late.fraud
    assert [e.event_id for e in baseline.canonical_events] == [
        e.event_id for e in no_late.canonical_events
    ]
    assert [e.occurred_at for e in baseline.canonical_events] == [
        e.occurred_at for e in no_late.canonical_events
    ]
    assert [e.payload for e in baseline.canonical_events] == [
        e.payload for e in no_late.canonical_events
    ]
    assert {d.event.event_id for d in baseline.delivery_records if d.attempt == 2} == {
        d.event.event_id for d in no_late.delivery_records if d.attempt == 2
    }
    more = run(replace(world(), fraud=replace(world().fraud, ring_count=2)))
    original = {e.event_id: e for e in baseline.canonical_events}
    added = {e.event_id: e for e in more.canonical_events}
    # Legitimate event-local draws survive a fraud config change.
    for event in baseline.legitimate.event_records:
        assert original[event.value.event_id] == added[event.value.event_id]
    enlarged = run(
        replace(world(), legitimate=replace(world().legitimate, user_count=4))
    )

    def transport_by_subject(result):
        return {
            (event.subject_id, event.event_type): (
                event.produced_at - event.occurred_at,
                any(
                    delivery.attempt == 2
                    and delivery.event.subject_id == event.subject_id
                    and delivery.event.event_type == event.event_type
                    for delivery in result.delivery_records
                ),
            )
            for event in result.canonical_events
        }

    original_transport = transport_by_subject(baseline)
    larger_transport = transport_by_subject(enlarged)
    assert all(
        larger_transport[key] == value for key, value in original_transport.items()
    )
    more_fraud_transport = transport_by_subject(more)
    assert all(
        more_fraud_transport[key] == value for key, value in original_transport.items()
    )
    assert all(e.produced_at >= e.occurred_at for e in baseline.canonical_events)
    assert all(
        traffic().min_production_delay
        <= e.produced_at - e.occurred_at
        <= traffic().max_production_delay
        for e in baseline.canonical_events
        if e.produced_at > e.occurred_at
    )


def test_order_summary_and_projector_convergence():
    result = run(
        behavior=traffic(late_event_probability=1, min_production_delay=timedelta(0))
    )
    events = result.canonical_events
    deliveries = result.delivery_records
    assert len(events) == 7 + 2 * (9 + 12)
    assert len({e.event_id for e in events}) == len(events)
    assert [d.deliver_at for d in deliveries] == sorted(
        d.deliver_at for d in deliveries
    )
    first_seen = [d.event.occurred_at for d in deliveries if d.attempt == 1]
    assert any(a > b for a, b in zip(first_seen, first_seen[1:], strict=False))
    summary = result.traffic_summary
    assert summary.logical_event_count == len(events)
    assert summary.delivery_count == len(deliveries)
    assert summary.duplicate_delivery_count == len(deliveries) - len(events)
    assert summary.late_logical_event_count == sum(
        e.produced_at > e.occurred_at for e in events
    )
    assert sum(count for _, count in summary.delivery_buckets) == len(deliveries)
    assert [bucket for bucket, _ in summary.delivery_buckets] == sorted(
        bucket for bucket, _ in summary.delivery_buckets
    )
    reference = ReferenceFeatureProjector()
    delivered = ReferenceFeatureProjector()
    assert all(reference.apply(e) == ApplyResult.APPLIED for e in events)
    counts = Counter(delivered.apply(d.event) for d in deliveries)
    assert counts == {
        ApplyResult.APPLIED: len(events),
        ApplyResult.DUPLICATE: len(deliveries) - len(events),
    }
    for user in result.users:
        device = next(
            (
                e.payload.device_id
                for e in events
                if e.event_type == "account.created"
                and e.payload.user_id == user.user_id
            ),
            None,
        )
        for at in (START + timedelta(minutes=1), summary.latest_occurred_at):
            assert reference.features_for(
                user_id=user.user_id, device_id=device, as_of=at
            ) == delivered.features_for(
                user_id=user.user_id, device_id=device, as_of=at
            )
    for user, device in zip(
        result.legitimate.users, result.legitimate.devices, strict=True
    ):
        assert (
            reference.features_for(
                user_id=user.user_id,
                device_id=device.device_id,
                as_of=summary.latest_occurred_at,
            ).accounts_on_device
            == 1
        )
    ring = result.fraud.ring_truth[0]
    ring_features = reference.features_for(
        user_id=ring.member_user_ids[0],
        device_id=ring.shared_device_id,
        as_of=START + timedelta(minutes=1),
    )
    assert ring_features.accounts_on_device == 4
    assert ring_features.payments_10m == 3
    assert ring_features.failed_payments_1h == 3
    for alternative in (
        run(
            behavior=traffic(late_event_probability=0, duplicate_delivery_probability=0)
        ),
        run(
            behavior=traffic(late_event_probability=1, duplicate_delivery_probability=1)
        ),
    ):
        projector = ReferenceFeatureProjector()
        for delivery in alternative.delivery_records:
            projector.apply(delivery.event)
        devices = {
            e.payload.user_id: e.payload.device_id
            for e in events
            if e.event_type == "account.created"
        }
        for user in result.users:
            assert reference.features_for(
                user_id=user.user_id,
                device_id=devices[user.user_id],
                as_of=summary.latest_occurred_at,
            ) == projector.features_for(
                user_id=user.user_id,
                device_id=devices[user.user_id],
                as_of=summary.latest_occurred_at,
            )
