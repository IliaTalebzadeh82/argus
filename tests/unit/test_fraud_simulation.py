"""Coordinated fraud behavior and simulator/production boundary."""

from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from argus.events.features import ApplyResult, ReferenceFeatureProjector
from argus.events.fraud import FRAUD_CONTRACTS, validate_fraud_event
from argus.simulation.config import SimulationConfig
from argus.simulation.fraud_world import FraudScenarioConfig, run_fraud_scenario
from argus.simulation.kernel import SIMULATOR_VERSION, SimulationKernel

START = datetime(2026, 1, 1, tzinfo=UTC)


def config(**changes: object) -> FraudScenarioConfig:
    defaults = dict(
        ring_count=2,
        accounts_per_ring=4,
        payments_per_account=5,
        merchant_count=5,
        payment_failure_probability=0.4,
        chargeback_probability=0.6,
        min_amount_minor=100,
        max_amount_minor=10_000,
        currency="usd",
        ring_spacing=timedelta(hours=1),
        account_spacing=timedelta(seconds=10),
        first_payment_delay=timedelta(minutes=1),
        payment_spacing=timedelta(minutes=1),
        terminal_delay=timedelta(seconds=5),
        chargeback_delay=timedelta(days=2),
    )
    return FraudScenarioConfig(**(defaults | changes))


def run(scenario: FraudScenarioConfig | None = None, *, seed: int = 17, start=START):
    return run_fraud_scenario(
        SimulationKernel(SimulationConfig(seed=seed, starts_at=start)),
        scenario or config(),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("ring_count", 0),
        ("ring_count", True),
        ("accounts_per_ring", 1),
        ("accounts_per_ring", False),
        ("payments_per_account", -1),
        ("payments_per_account", True),
        ("merchant_count", 0),
        ("merchant_count", False),
        ("min_amount_minor", -1),
        ("min_amount_minor", True),
        ("max_amount_minor", 99),
        ("max_amount_minor", False),
        ("currency", "US"),
        ("payment_failure_probability", -0.1),
        ("payment_failure_probability", 1.1),
        ("payment_failure_probability", float("nan")),
        ("payment_failure_probability", float("inf")),
        ("payment_failure_probability", True),
        ("chargeback_probability", -0.1),
        ("chargeback_probability", 1.1),
        ("chargeback_probability", float("nan")),
        ("chargeback_probability", float("-inf")),
        ("chargeback_probability", True),
        ("ring_spacing", timedelta(seconds=-1)),
        ("account_spacing", timedelta(seconds=-1)),
        ("first_payment_delay", timedelta(seconds=-1)),
        ("payment_spacing", timedelta(seconds=-1)),
        ("terminal_delay", timedelta(seconds=-1)),
        ("chargeback_delay", timedelta(seconds=-1)),
    ],
)
def test_invalid_config(field, value):
    with pytest.raises((TypeError, ValueError)):
        config(**{field: value})


def test_canonical_reproduction_and_seed_time_separation():
    scenario = config()
    assert scenario.currency == "USD"
    assert scenario.to_json() == replace(scenario, currency="USD").to_json()
    assert '"chargeback_delay_us":172800000000' in scenario.to_json()
    baseline = run(scenario)
    assert baseline == run(scenario)
    assert baseline.manifest.simulator_version == SIMULATOR_VERSION == 1
    other_seed = run(scenario, seed=18)
    shifted = run(scenario, start=START + timedelta(days=1))
    assert [(tx.amount, tx.merchant_id) for tx in baseline.transactions] != [
        (tx.amount, tx.merchant_id) for tx in other_seed.transactions
    ]
    assert [tx.amount for tx in baseline.transactions] == [
        tx.amount for tx in shifted.transactions
    ]
    assert (
        baseline.event_records[0].value.event_id
        != other_seed.event_records[0].value.event_id
    )
    assert (
        baseline.event_records[0].value.event_id
        != shifted.event_records[0].value.event_id
    )
    assert shifted.users[0].created_at - baseline.users[0].created_at == timedelta(
        days=1
    )


def test_structure_relationships_contracts_and_chronology():
    result = run()
    events = [record.value for record in result.event_records]
    counts = Counter(event.event_type for event in events)
    assert (
        len(result.users),
        len(result.devices),
        len(result.transactions),
        len(result.payment_attempts),
    ) == (8, 2, 40, 40)
    assert counts["account.created"] == 8
    assert counts["payment.attempted"] == 40
    assert counts["payment.failed"] + counts["transaction.completed"] == 40
    assert counts["chargeback.received"] <= counts["transaction.completed"]
    assert set(counts) == set(FRAUD_CONTRACTS)
    assert len(set(event.event_id for event in events)) == len(events)
    assert all(
        isinstance(event.event_id, UUID) and event.event_id.version == 5
        for event in events
    )
    assert [event.occurred_at for event in events] == sorted(
        event.occurred_at for event in events
    )
    assert [record.sequence for record in result.event_records] == list(
        range(1, len(events) + 1)
    )
    assert all(
        record.generated_at == event.produced_at == event.occurred_at
        for record, event in zip(result.event_records, events, strict=True)
    )
    user_ids = {user.user_id for user in result.users}
    transaction_by_id = {tx.transaction_id: tx for tx in result.transactions}
    assert len(result.ring_truth) == 2
    assert len(result.card_uses) == 40
    assert len(result.promo_redemptions) == 8
    assert len({device.device_id for device in result.devices}) == 2
    for ring_index, ring in enumerate(result.ring_truth):
        assert len(set(ring.member_user_ids)) == 4
        assert set(ring.member_user_ids) <= user_ids
        assert result.devices[ring_index].device_id == ring.shared_device_id
        assert (
            result.devices[ring_index].first_seen_at
            == START + ring_index * result.config.ring_spacing
        )
        accounts = [
            event
            for event in events
            if event.event_type == "account.created"
            and event.payload.user_id in ring.member_user_ids
        ]
        assert len(accounts) == 4
        assert {event.payload.device_id for event in accounts} == {
            ring.shared_device_id
        }
        for member_index, member in enumerate(ring.member_user_ids):
            user = next(user for user in result.users if user.user_id == member)
            assert (
                user.created_at
                == START
                + ring_index * result.config.ring_spacing
                + member_index * result.config.account_spacing
            )
        uses = [use for use in result.card_uses if use.ring_id == ring.ring_id]
        assert len({use.user_id for use in uses}) == 4
        assert {use.card_id for use in uses} == {ring.shared_card_id}
        redemptions = [
            promo for promo in result.promo_redemptions if promo.ring_id == ring.ring_id
        ]
        assert len({promo.user_id for promo in redemptions}) == 4
        assert {promo.promo_code for promo in redemptions} == {ring.shared_promo_code}
    for use in result.card_uses:
        assert use.user_id in user_ids
        assert transaction_by_id[use.transaction_id].user_id == use.user_id
    for redemption in result.promo_redemptions:
        assert redemption.user_id in user_ids
        assert (
            transaction_by_id[redemption.transaction_id].user_id == redemption.user_id
        )
        assert (
            transaction_by_id[redemption.transaction_id].created_at
            == redemption.redeemed_at
        )
    for attempt, tx in zip(result.payment_attempts, result.transactions, strict=True):
        assert attempt.transaction_id == tx.transaction_id
        assert attempt.attempted_at == tx.created_at
        user = next(user for user in result.users if user.user_id == tx.user_id)
        assert (
            tx.created_at
            == user.created_at
            + result.config.first_payment_delay
            + (result.transactions.index(tx) % 5) * result.config.payment_spacing
        )
    forbidden = ("fraud", "ring_id", "card_id", "shared_card", "promo", "ground_truth")
    payload_fields = {
        "account.created": {"user_id", "device_id"},
        "payment.attempted": {"payment_id", "transaction_id", "user_id"},
        "payment.failed": {"payment_id", "transaction_id", "user_id"},
        "transaction.completed": {"transaction_id", "user_id"},
        "chargeback.received": {"chargeback_id", "transaction_id", "user_id"},
    }
    for event in events:
        validate_fraud_event(event)
        assert event.subject_id.startswith(
            ("user-", "payment-", "transaction-", "chargeback-")
        )
        assert all(word not in event.model_dump_json() for word in forbidden)
        assert set(event.payload.model_dump()) == payload_fields[event.event_type]


def test_ring_locality_and_random_dimension_independence():
    baseline = run()
    extended = run(config(ring_count=3))
    assert baseline.ring_truth == extended.ring_truth[:2]
    assert baseline.transactions == extended.transactions[:40]
    assert baseline.card_uses == extended.card_uses[:40]
    assert baseline.promo_redemptions == extended.promo_redemptions[:8]
    assert (
        baseline.event_records[0].value.event_id
        != extended.event_records[0].value.event_id
    )

    def outcomes(result):
        return [
            (event.event_type, event.payload.transaction_id)
            for record in result.event_records
            if (event := record.value).event_type
            in ("payment.failed", "transaction.completed", "chargeback.received")
        ]

    amount_changed = run(config(min_amount_minor=1, max_amount_minor=2))
    assert [tx.merchant_id for tx in baseline.transactions] == [
        tx.merchant_id for tx in amount_changed.transactions
    ]
    assert outcomes(baseline) == outcomes(amount_changed)
    chargeback_changed = run(config(chargeback_probability=0))
    assert [(tx.amount, tx.merchant_id) for tx in baseline.transactions] == [
        (tx.amount, tx.merchant_id) for tx in chargeback_changed.transactions
    ]
    assert [
        entry for entry in outcomes(baseline) if entry[0] != "chargeback.received"
    ] == outcomes(chargeback_changed)
    merchant_changed = run(config(merchant_count=6))
    assert [tx.amount for tx in baseline.transactions] == [
        tx.amount for tx in merchant_changed.transactions
    ]
    assert outcomes(baseline) == outcomes(merchant_changed)


def test_boundaries_causality_and_equal_time_ties():
    failed = run(config(payment_failure_probability=1, chargeback_probability=1))
    assert (
        Counter(record.value.event_type for record in failed.event_records)[
            "payment.failed"
        ]
        == 40
    )
    assert not any(
        record.value.event_type in ("transaction.completed", "chargeback.received")
        for record in failed.event_records
    )
    all_chargeback = run(
        config(payment_failure_probability=0, chargeback_probability=1)
    )
    events = [record.value for record in all_chargeback.event_records]
    assert Counter(event.event_type for event in events)["transaction.completed"] == 40
    assert Counter(event.event_type for event in events)["chargeback.received"] == 40
    completed = {
        event.payload.transaction_id: event
        for event in events
        if event.event_type == "transaction.completed"
    }
    for event in events:
        if event.event_type == "chargeback.received":
            origin = completed[event.payload.transaction_id]
            assert event.payload.user_id == origin.payload.user_id
            assert event.trace_id == origin.trace_id
            assert event.occurred_at - origin.occurred_at == timedelta(days=2)
            assert events.index(origin) < events.index(event)
    assert not any(
        record.value.event_type == "chargeback.received"
        for record in run(config(chargeback_probability=0)).event_records
    )
    tied = run(
        config(
            ring_count=1,
            accounts_per_ring=2,
            payments_per_account=1,
            payment_failure_probability=0,
            chargeback_probability=1,
            ring_spacing=timedelta(0),
            account_spacing=timedelta(0),
            first_payment_delay=timedelta(0),
            payment_spacing=timedelta(0),
            terminal_delay=timedelta(0),
            chargeback_delay=timedelta(0),
        )
    )
    assert [record.value.event_type for record in tied.event_records] == [
        "account.created",
        "payment.attempted",
        "transaction.completed",
        "chargeback.received",
        "account.created",
        "payment.attempted",
        "transaction.completed",
        "chargeback.received",
    ]
    assert tied == run(tied.config)


def test_zero_payments_and_reference_features():
    empty = run(config(payments_per_account=0))
    assert empty.card_uses == empty.promo_redemptions == empty.transactions == ()
    assert all(
        record.value.event_type == "account.created" for record in empty.event_records
    )
    result = run(
        config(
            ring_count=1,
            payment_failure_probability=1,
            chargeback_probability=1,
            account_spacing=timedelta(0),
            first_payment_delay=timedelta(0),
            payment_spacing=timedelta(minutes=1),
            terminal_delay=timedelta(0),
        )
    )
    projector = ReferenceFeatureProjector()
    for record in result.event_records:
        assert projector.apply(record.value) == ApplyResult.APPLIED
    for user in result.users:
        snapshot = projector.features_for(
            user_id=user.user_id,
            device_id=result.devices[0].device_id,
            as_of=START + timedelta(minutes=4),
        )
        assert (
            snapshot.accounts_on_device,
            snapshot.payments_10m,
            snapshot.failed_payments_1h,
        ) == (4, 5, 5)
