"""Real Redis comparisons against the CP01 in-memory correctness oracle."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from argus.events.envelope import EventEnvelope
from argus.events.features import (
    ApplyResult,
    EventIdentityConflict,
    ReferenceFeatureProjector,
)
from argus.events.fraud import (
    AccountCreatedPayload,
    ChargebackReceivedPayload,
    PaymentAttemptedPayload,
    PaymentFailedPayload,
    TransactionCompletedPayload,
)
from argus.features.redis_projection import (
    ProjectionStateError,
    ProjectionUnavailable,
    RedisFeatureProjector,
    create_redis_client,
)

T = datetime(2026, 10, 14, 12, tzinfo=UTC)


@pytest.fixture
def projection() -> RedisFeatureProjector:
    url = os.environ.get("ARGUS_REDIS_URL")
    if not url:
        pytest.fail("ARGUS_REDIS_URL is required for Redis integration tests")
    client = create_redis_client(url)
    namespace = f"argus:features:v1:test:{uuid4().hex}:"
    try:
        client.ping()
        yield RedisFeatureProjector(client, namespace=namespace)
    finally:
        keys = list(client.scan_iter(f"{namespace}*"))
        if keys:
            client.delete(*keys)
        client.close()


def event(
    number: int, kind: str, payload: object, *, at: datetime = T, produced: datetime = T
) -> EventEnvelope:
    subjects = {
        "account.created": "user_id",
        "payment.attempted": "payment_id",
        "payment.failed": "payment_id",
        "transaction.completed": "transaction_id",
        "chargeback.received": "chargeback_id",
    }
    return EventEnvelope[type(payload)](
        event_id=UUID(int=number),
        event_type=kind,
        event_version=1,
        occurred_at=at,
        produced_at=produced,
        producer="test",
        trace_id="trace",
        subject_id=getattr(payload, subjects[kind]),
        payload=payload,
    )


def attempt(number: int, at: datetime = T, user: str = "u") -> EventEnvelope:
    return event(
        number,
        "payment.attempted",
        PaymentAttemptedPayload(
            payment_id=f"p{number}", transaction_id="t", user_id=user
        ),
        at=at,
    )


def failure(number: int, at: datetime = T) -> EventEnvelope:
    return event(
        number,
        "payment.failed",
        PaymentFailedPayload(payment_id=f"p{number}", transaction_id="t", user_id="u"),
        at=at,
    )


def account(number: int, user: str, at: datetime, device: str = "d") -> EventEnvelope:
    return event(
        number,
        "account.created",
        AccountCreatedPayload(user_id=user, device_id=device),
        at=at,
    )


def assert_matches(
    projection: RedisFeatureProjector,
    reference: ReferenceFeatureProjector,
    *,
    user: str = "u",
    device: str | None = "d",
    at: datetime = T,
) -> None:
    assert projection.features_for(
        user_id=user, device_id=device, as_of=at
    ) == reference.features_for(user_id=user, device_id=device, as_of=at)


def test_lifecycle(projection: RedisFeatureProjector) -> None:
    with pytest.raises(ProjectionUnavailable, match="UNINITIALIZED"):
        projection.features_for(user_id="u", device_id="d", as_of=T)
    with pytest.raises(ProjectionUnavailable, match="UNINITIALIZED"):
        projection.apply(attempt(1))
    with pytest.raises(ProjectionStateError):
        projection.mark_ready()
    projection.begin_rebuild()
    with pytest.raises(ProjectionStateError):
        projection.begin_rebuild()
    projection.apply(attempt(1))
    with pytest.raises(ProjectionUnavailable, match="REBUILDING"):
        projection.features_for(user_id="u", device_id="d", as_of=T)
    projection.mark_ready()
    with pytest.raises(ProjectionStateError):
        projection.mark_ready()
    with pytest.raises(ProjectionStateError):
        projection.begin_rebuild()
    assert (
        projection.features_for(user_id="u", device_id="d", as_of=T).payments_10m == 1
    )
    assert projection.apply(attempt(2)) == ApplyResult.APPLIED


def test_windows_microseconds_and_missing_device(
    projection: RedisFeatureProjector,
) -> None:
    projection.begin_rebuild()
    reference = ReferenceFeatureProjector()
    times = [
        T - timedelta(minutes=10, microseconds=1),
        T - timedelta(minutes=10),
        T - timedelta(minutes=10) + timedelta(microseconds=1),
        T,
        T + timedelta(microseconds=1),
    ]
    failed_times = [
        T - timedelta(hours=1, microseconds=1),
        T - timedelta(hours=1),
        T - timedelta(hours=1) + timedelta(microseconds=1),
        T,
        T + timedelta(microseconds=1),
    ]
    for number, at in enumerate(times, 1):
        item = attempt(number, at)
        assert projection.apply(item) == reference.apply(item)
    for number, at in enumerate(failed_times, 6):
        item = failure(number, at)
        assert projection.apply(item) == reference.apply(item)
    projection.mark_ready()
    assert_matches(projection, reference, device=None)
    assert_matches(projection, reference, device="unseen")
    assert (
        projection.features_for(user_id="u", device_id=None, as_of=T).payments_10m == 2
    )
    assert (
        projection.features_for(user_id="u", device_id=None, as_of=T).failed_payments_1h
        == 2
    )


def test_replay_out_of_order_and_historical_device(
    projection: RedisFeatureProjector,
) -> None:
    projection.begin_rebuild()
    reference = ReferenceFeatureProjector()
    history = [
        account(1, "a", T),
        account(2, "a", T - timedelta(hours=2)),
        account(3, "b", T - timedelta(hours=1)),
        attempt(4, T - timedelta(minutes=2)),
        failure(5, T - timedelta(minutes=3)),
    ]
    for item in (
        history[0],
        history[3],
        history[3],
        history[4],
        history[1],
        history[0],
        history[2],
    ):
        assert projection.apply(item) == reference.apply(item)
    projection.mark_ready()
    for at in (
        T - timedelta(hours=3),
        T - timedelta(minutes=90),
        T - timedelta(minutes=30),
        T,
    ):
        assert_matches(projection, reference, user="a", at=at)
        assert_matches(projection, reference, at=at)
    assert (
        projection.features_for(
            user_id="a", device_id="d", as_of=T - timedelta(minutes=90)
        ).accounts_on_device
        == 1
    )
    unique = ReferenceFeatureProjector()
    for item in history:
        unique.apply(item)
    assert reference.features_for(
        user_id="u", device_id="d", as_of=T
    ) == unique.features_for(user_id="u", device_id="d", as_of=T)


def test_conflict_preserves_original(projection: RedisFeatureProjector) -> None:
    projection.begin_rebuild()
    original = attempt(1)
    projection.apply(original)
    projection.mark_ready()
    before = projection.features_for(user_id="u", device_id=None, as_of=T)
    for changed in (
        attempt(1, user="other"),
        event(
            1, "payment.attempted", original.payload, produced=T + timedelta(seconds=1)
        ),
    ):
        with pytest.raises(EventIdentityConflict):
            projection.apply(changed)
    assert projection.features_for(user_id="u", device_id=None, as_of=T) == before
    assert projection.apply(original) == ApplyResult.DUPLICATE


def test_concurrent_duplicate(projection: RedisFeatureProjector) -> None:
    projection.begin_rebuild()
    projection.mark_ready()
    item = attempt(1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(projection.apply, (item, item)))
    assert sorted(results) == [ApplyResult.APPLIED, ApplyResult.DUPLICATE]
    reference = ReferenceFeatureProjector()
    reference.apply(item)
    assert_matches(projection, reference, device=None)


def test_no_feature_events_still_deduplicate(projection: RedisFeatureProjector) -> None:
    projection.begin_rebuild()
    reference = ReferenceFeatureProjector()
    events = [
        event(
            1,
            "transaction.completed",
            TransactionCompletedPayload(transaction_id="t", user_id="u"),
        ),
        event(
            2,
            "chargeback.received",
            ChargebackReceivedPayload(
                chargeback_id="c", transaction_id="t", user_id="u"
            ),
        ),
    ]
    for item in events:
        assert projection.apply(item) == reference.apply(item)
        assert projection.apply(item) == reference.apply(item)
        with pytest.raises(EventIdentityConflict):
            projection.apply(
                event(
                    item.event_id.int,
                    item.event_type,
                    item.payload,
                    produced=T + timedelta(seconds=1),
                )
            )
    projection.mark_ready()
    assert_matches(projection, reference)


def test_precision_guard_and_operational_failure(
    projection: RedisFeatureProjector,
) -> None:
    projection.begin_rebuild()
    with pytest.raises(ValueError, match="exact Redis"):
        projection.apply(attempt(1, datetime(9999, 1, 1, tzinfo=UTC)))
    projection.mark_ready()
    with pytest.raises(ValueError, match="exact Redis"):
        projection.features_for(
            user_id="u", device_id="d", as_of=datetime(9999, 1, 1, tzinfo=UTC)
        )
    broken = RedisFeatureProjector(
        create_redis_client("redis://127.0.0.1:1/0"), namespace=projection.namespace
    )
    with pytest.raises(RedisConnectionError):
        broken.features_for(user_id="u", device_id="d", as_of=T)
    broken.client.close()
