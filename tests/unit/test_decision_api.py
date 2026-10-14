"""Offline facts, provenance, and feature boundary checks."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from argus.apps.decision_api.main import PaymentDecisionRequest
from argus.apps.decision_api.service import (
    DEPLOYED_POLICY,
    DEPLOYED_RULES,
    FEATURE_SOURCE,
    PaymentDecisionInput,
    fingerprint,
    signals_from,
)
from argus.events.features import OnlineFeatureSnapshot

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def facts(currency="usd", time=NOW):
    return {
        "user": {"user_id": "u", "created_at": time},
        "transaction": {
            "transaction_id": "t",
            "user_id": "u",
            "merchant_id": "m",
            "amount": {"amount_minor": 100, "currency": currency},
            "created_at": time,
        },
        "payment_attempt": {
            "payment_id": "p",
            "transaction_id": "t",
            "attempted_at": time,
        },
        "devices": [{"device_id": "a", "first_seen_at": time}],
        "observed_device_id": "a",
    }


def test_fingerprint_covers_facts_and_normalizes_values():
    a = PaymentDecisionInput.model_validate(facts())
    b = PaymentDecisionInput.model_validate(facts("USD", "2026-01-02T03:30:00+03:30"))
    assert fingerprint(a) == fingerprint(b)
    changed = facts()
    changed["observed_device_id"] = None
    assert fingerprint(a) != fingerprint(PaymentDecisionInput.model_validate(changed))
    changed = facts()
    changed["devices"].append({"device_id": "b", "first_seen_at": NOW})
    assert fingerprint(a) != fingerprint(PaymentDecisionInput.model_validate(changed))


def test_request_rejects_caller_evidence_and_metadata():
    for field in (
        "risk_signals",
        "rule_set_version",
        "policy_version",
        "action",
        "decision_id",
    ):
        value = facts()
        value[field] = []
        with pytest.raises(ValidationError):
            PaymentDecisionRequest.model_validate({"facts": value})
    with pytest.raises(ValidationError):
        PaymentDecisionRequest.model_validate({"context": facts()})


def test_observed_device_validation_and_no_device():
    assert PaymentDecisionInput.model_validate(facts()).observed_device_id == "a"
    value = facts()
    value["observed_device_id"] = "b"
    with pytest.raises(ValidationError):
        PaymentDecisionInput.model_validate(value)
    value["devices"] = []
    value["observed_device_id"] = None
    assert PaymentDecisionInput.model_validate(value).observed_device_id is None


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["transaction"].update(user_id="wrong"),
        lambda value: value["payment_attempt"].update(transaction_id="wrong"),
        lambda value: value["transaction"]["amount"].update(amount_minor=-1),
        lambda value: value["user"].update(created_at="2026-01-02T00:00:00"),
    ],
)
def test_invalid_facts(change):
    value = facts()
    change(value)
    with pytest.raises(ValidationError):
        PaymentDecisionInput.model_validate(value)


def test_signal_adaptation_and_versions():
    snapshot = OnlineFeatureSnapshot(
        user_id="u",
        device_id="a",
        as_of=NOW,
        payments_10m=5,
        failed_payments_1h=3,
        accounts_on_device=2,
    )
    signals = signals_from(snapshot)
    assert [(s.code, s.value, s.source, s.observed_at) for s in signals] == [
        ("payments_10m", 5, FEATURE_SOURCE, NOW),
        ("failed_payments_1h", 3, FEATURE_SOURCE, NOW),
        ("accounts_on_device", 2, FEATURE_SOURCE, NOW),
    ]
    assert (
        len(signals_from(snapshot.model_copy(update={"accounts_on_device": None}))) == 2
    )
    assert DEPLOYED_RULES.rule_set_version == 2
    assert all(
        rule.source == FEATURE_SOURCE and rule.rule_version == 1
        for rule in DEPLOYED_RULES.rules
    )
    assert DEPLOYED_POLICY.policy_version == 1
