"""Pure request normalization and boundary behavior."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from argus.apps.decision_api.service import fingerprint
from argus.domain.models import DecisionContext

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def context(currency="usd", time=NOW, count=1):
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
        "risk_signals": [
            {
                "code": "payments_10m",
                "value": count,
                "observed_at": time,
                "source": "caller",
            },
        ],
    }


def test_fingerprint_normalizes_semantic_values():
    a = DecisionContext.model_validate(context())
    b = DecisionContext.model_validate(context("USD", "2026-01-02T03:30:00+03:30"))
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a) != fingerprint(
        DecisionContext.model_validate(context(count=2))
    )


def test_fingerprint_preserves_signal_order():
    value = context()
    value["risk_signals"].append(
        {
            "code": "accounts_on_device",
            "value": 2,
            "observed_at": NOW,
            "source": "caller",
        }
    )
    forward = DecisionContext.model_validate(value)
    value["risk_signals"].reverse()
    backward = DecisionContext.model_validate(value)
    assert fingerprint(forward) != fingerprint(backward)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["transaction"].update(user_id="wrong"),
        lambda value: value["payment_attempt"].update(transaction_id="wrong"),
        lambda value: value["transaction"]["amount"].update(amount_minor=-1),
        lambda value: value["user"].update(created_at="2026-01-02T00:00:00"),
    ],
)
def test_invalid_context(change):
    value = context()
    change(value)
    with pytest.raises(ValidationError):
        DecisionContext.model_validate(value)
