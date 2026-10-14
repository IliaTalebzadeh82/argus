"""Behavioral and production-contract checks for the legitimate baseline."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from argus.events.features import ApplyResult, ReferenceFeatureProjector
from argus.events.fraud import validate_fraud_event
from argus.simulation.config import SimulationConfig
from argus.simulation.kernel import SIMULATOR_VERSION, SimulationKernel
from argus.simulation.legitimate import (
    LegitimateScenarioConfig,
    run_legitimate_scenario,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def config(**changes: object) -> LegitimateScenarioConfig:
    defaults = dict(
        user_count=3,
        payments_per_user=4,
        merchant_count=5,
        payment_failure_probability=0.5,
        min_amount_minor=100,
        max_amount_minor=10000,
        currency="usd",
        account_spacing=timedelta(minutes=1),
        first_payment_delay=timedelta(minutes=2),
        payment_spacing=timedelta(minutes=3),
        terminal_delay=timedelta(seconds=5),
    )
    return LegitimateScenarioConfig(**(defaults | changes))


def run(
    scenario: LegitimateScenarioConfig | None = None,
    *,
    seed: int = 17,
    start: datetime = START,
):
    return run_legitimate_scenario(
        SimulationKernel(SimulationConfig(seed=seed, starts_at=start)),
        scenario or config(),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_count", 0),
        ("user_count", True),
        ("payments_per_user", -1),
        ("payments_per_user", False),
        ("merchant_count", 0),
        ("payment_failure_probability", -0.1),
        ("payment_failure_probability", 1.1),
        ("payment_failure_probability", float("nan")),
        ("payment_failure_probability", float("inf")),
        ("min_amount_minor", -1),
        ("max_amount_minor", 99),
        ("currency", "US"),
        ("account_spacing", timedelta(seconds=-1)),
        ("first_payment_delay", timedelta(seconds=-1)),
        ("payment_spacing", timedelta(seconds=-1)),
        ("terminal_delay", timedelta(seconds=-1)),
    ],
)
def test_invalid_config(field: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        config(**{field: value})


def test_config_canonical_and_full_reproduction() -> None:
    scenario = config()
    assert scenario.currency == "USD"
    assert scenario.to_json() == replace(scenario, currency="USD").to_json()
    assert '"terminal_delay_us":5000000' in scenario.to_json()
    assert run(scenario) == run(scenario)
    assert run(scenario).manifest.simulator_version == SIMULATOR_VERSION == 1
    assert (
        run(replace(scenario, merchant_count=6)).config.to_json() != scenario.to_json()
    )


def test_structure_contracts_and_chronology() -> None:
    result = run()
    assert len(result.users) == len(result.devices) == 3
    assert len(set(device.device_id for device in result.devices)) == 3
    assert len(result.transactions) == len(result.payment_attempts) == 12
    assert len(result.event_records) == 27
    events = [record.value for record in result.event_records]
    assert len(set(event.event_id for event in events)) == 27
    assert all(isinstance(event.event_id, UUID) for event in events)
    assert [event.occurred_at for event in events] == sorted(
        event.occurred_at for event in events
    )
    assert [record.sequence for record in result.event_records] == list(range(1, 28))
    assert all(
        record.generated_at == event.produced_at == event.occurred_at
        for record, event in zip(result.event_records, events, strict=True)
    )
    assert sum(event.event_type == "account.created" for event in events) == 3
    assert sum(event.event_type == "payment.attempted" for event in events) == 12
    assert (
        sum(
            event.event_type in ("payment.failed", "transaction.completed")
            for event in events
        )
        == 12
    )
    for event in events:
        validate_fraud_event(event)
    for user, device in zip(result.users, result.devices, strict=True):
        assert device.first_seen_at == user.created_at
        index = result.users.index(user)
        assert user.created_at == START + index * result.config.account_spacing
        account = next(
            event
            for event in events
            if event.event_type == "account.created"
            and event.subject_id == user.user_id
        )
        assert account.payload.device_id == device.device_id
    for transaction, attempt in zip(
        result.transactions, result.payment_attempts, strict=True
    ):
        assert attempt.transaction_id == transaction.transaction_id
        assert transaction.user_id in {user.user_id for user in result.users}
        user = next(
            user for user in result.users if user.user_id == transaction.user_id
        )
        payment_index = (
            result.payment_attempts.index(attempt) % result.config.payments_per_user
        )
        assert (
            attempt.attempted_at
            == transaction.created_at
            == (
                user.created_at
                + result.config.first_payment_delay
                + payment_index * result.config.payment_spacing
            )
        )
        payment_events = [
            event
            for event in events
            if event.trace_id == f"payment:{attempt.payment_id}"
        ]
        assert len(payment_events) == 2
        assert {event.event_type for event in payment_events} & {
            "payment.failed",
            "transaction.completed",
        }
        assert (
            payment_events[1].occurred_at - payment_events[0].occurred_at
            == result.config.terminal_delay
        )


@pytest.mark.parametrize(
    "probability,terminal", [(0, "transaction.completed"), (1, "payment.failed")]
)
def test_boundary_outcomes(probability: float, terminal: str) -> None:
    result = run(config(payment_failure_probability=probability))
    terminals = [
        record.value.event_type
        for record in result.event_records
        if record.value.event_type in ("transaction.completed", "payment.failed")
    ]
    assert terminals == [terminal] * 12


def test_zero_payments_emits_accounts_only() -> None:
    result = run(config(payments_per_user=0))
    assert result.transactions == result.payment_attempts == ()
    assert [record.value.event_type for record in result.event_records] == [
        "account.created"
    ] * 3


def test_seed_time_and_population_locality() -> None:
    small = run()
    other_seed = run(seed=18)
    shifted = run(start=START + timedelta(days=1))
    large = run(config(user_count=4))

    def behavior(result):
        return tuple((tx.amount, tx.merchant_id) for tx in result.transactions)

    def outcomes(result):
        return tuple(
            record.value.event_type
            for record in result.event_records
            if record.value.event_type in ("payment.failed", "transaction.completed")
        )

    assert (behavior(small), outcomes(small)) != (
        behavior(other_seed),
        outcomes(other_seed),
    )
    assert (
        small.event_records[0].value.event_id
        != other_seed.event_records[0].value.event_id
    )
    assert behavior(small) == behavior(shifted)
    assert outcomes(small) == outcomes(shifted)
    assert shifted.users[0].created_at - small.users[0].created_at == timedelta(days=1)
    assert behavior(small) == behavior(large)[:12]
    assert (
        small.event_records[0].value.event_id != large.event_records[0].value.event_id
    )
    for user in small.users:
        assert [
            r.value.event_type
            for r in small.event_records
            if r.value.trace_id.startswith(f"payment:payment-{user.user_id}-")
        ] == [
            r.value.event_type
            for r in large.event_records
            if r.value.trace_id.startswith(f"payment:payment-{user.user_id}-")
        ]


def test_independent_random_dimensions_and_equal_time_ties() -> None:
    baseline = run(config(user_count=1, payments_per_user=5))
    amount_changed = run(
        config(
            user_count=1, payments_per_user=5, min_amount_minor=1, max_amount_minor=2
        )
    )
    assert [tx.merchant_id for tx in baseline.transactions] == [
        tx.merchant_id for tx in amount_changed.transactions
    ]

    def terminal_types(result):
        return [
            record.value.event_type
            for record in result.event_records
            if record.value.event_type in ("payment.failed", "transaction.completed")
        ]

    assert terminal_types(baseline) == terminal_types(amount_changed)
    tied = run(
        config(
            user_count=2,
            payments_per_user=1,
            account_spacing=timedelta(0),
            first_payment_delay=timedelta(0),
            terminal_delay=timedelta(0),
        )
    )
    assert [r.value.event_type for r in tied.event_records][:3] == [
        "account.created",
        "payment.attempted",
        terminal_types(tied)[0],
    ]


def test_reference_projector_baseline() -> None:
    result = run(
        config(
            user_count=2,
            payments_per_user=3,
            payment_failure_probability=1,
            account_spacing=timedelta(0),
            first_payment_delay=timedelta(0),
            payment_spacing=timedelta(minutes=1),
            terminal_delay=timedelta(0),
        )
    )
    projector = ReferenceFeatureProjector()
    for record in result.event_records:
        assert projector.apply(record.value) == ApplyResult.APPLIED
    for user, device in zip(result.users, result.devices, strict=True):
        snapshot = projector.features_for(
            user_id=user.user_id,
            device_id=device.device_id,
            as_of=START + timedelta(minutes=2),
        )
        assert (
            snapshot.accounts_on_device,
            snapshot.payments_10m,
            snapshot.failed_payments_1h,
        ) == (1, 3, 3)
