"""Redis-backed projection of the CP01 fraud feature semantics."""

from datetime import UTC, datetime, timedelta

from redis import Redis

from argus.domain.models import Timestamp
from argus.events.envelope import EventEnvelope
from argus.events.features import (
    ApplyResult,
    EventIdentityConflict,
    OnlineFeatureSnapshot,
    canonical_event_identity,
)
from argus.events.fraud import AccountCreatedPayload, FraudPayload, validate_fraud_event

NAMESPACE = "argus:features:v1:"
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
MAX_EXACT_SCORE = 2**53


def create_redis_client(redis_url: str) -> Redis:
    """Construct a pooled synchronous client without connecting at import time."""
    return Redis.from_url(redis_url, decode_responses=True)


def _score(value: datetime) -> int:
    delta = value - EPOCH
    microseconds = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    if abs(microseconds) > MAX_EXACT_SCORE:
        raise ValueError("event time exceeds exact Redis sorted-set score range")
    return microseconds


_BEGIN = """
if redis.call('EXISTS', KEYS[1]) ~= 0 then return 'INVALID' end
redis.call('SET', KEYS[1], 'REBUILDING')
return 'REBUILDING'
"""

_READY = """
if redis.call('GET', KEYS[1]) ~= 'REBUILDING' then return 'INVALID' end
redis.call('SET', KEYS[1], 'READY')
return 'READY'
"""

_APPLY = """
local state = redis.call('GET', KEYS[1])
if state == false then return 'UNINITIALIZED' end
if state ~= 'REBUILDING' and state ~= 'READY' then return 'INVALID_STATE' end
local previous = redis.call('HGET', KEYS[2], ARGV[1])
if previous ~= false then
    if previous == ARGV[2] then return 'DUPLICATE' end
    return 'CONFLICT'
end
if ARGV[3] == 'payment.attempted' then
    redis.call('ZADD', KEYS[3], ARGV[4], ARGV[1])
elseif ARGV[3] == 'payment.failed' then
    redis.call('ZADD', KEYS[4], ARGV[4], ARGV[1])
elseif ARGV[3] == 'account.created' and ARGV[5] == '1' then
    local previous_score = redis.call('ZSCORE', KEYS[5], ARGV[6])
    if previous_score == false or tonumber(previous_score) > tonumber(ARGV[4]) then
        redis.call('ZADD', KEYS[5], ARGV[4], ARGV[6])
    end
end
redis.call('HSET', KEYS[2], ARGV[1], ARGV[2])
return 'APPLIED'
"""

_QUERY = """
local state = redis.call('GET', KEYS[1])
if state == false then return {'UNINITIALIZED'} end
if state ~= 'READY' then return {state} end
local payments = redis.call('ZCOUNT', KEYS[2], '(' .. ARGV[1], ARGV[3])
local failures = redis.call('ZCOUNT', KEYS[3], '(' .. ARGV[2], ARGV[3])
local accounts = -1
if ARGV[4] == '1' then
    accounts = redis.call('ZCOUNT', KEYS[4], '-inf', ARGV[3])
end
return {'READY', payments, failures, accounts}
"""


class ProjectionUnavailable(RuntimeError):
    """The projection is absent or still rebuilding."""


class ProjectionStateError(RuntimeError):
    """An invalid projection lifecycle transition or state."""


class RedisFeatureProjector:
    """A versioned, rebuildable Redis feature projection."""

    def __init__(self, client: Redis, *, namespace: str = NAMESPACE) -> None:
        if not namespace or not namespace.endswith(":"):
            raise ValueError("namespace must be non-empty and end in ':'")
        self.client = client
        self.namespace = namespace

    def _key(self, kind: str, identifier: str) -> str:
        # UTF-8 hex is injective for opaque identifiers, including ':' and Unicode.
        return f"{self.namespace}{kind}:{identifier.encode('utf-8').hex()}"

    @property
    def _state_key(self) -> str:
        return f"{self.namespace}state"

    @property
    def _identity_key(self) -> str:
        return f"{self.namespace}events"

    def begin_rebuild(self) -> None:
        if self.client.eval(_BEGIN, 1, self._state_key) != "REBUILDING":
            raise ProjectionStateError(
                "begin_rebuild requires an uninitialized projection"
            )

    def mark_ready(self) -> None:
        if self.client.eval(_READY, 1, self._state_key) != "READY":
            raise ProjectionStateError("mark_ready requires REBUILDING")

    def apply(self, event: EventEnvelope[FraudPayload]) -> ApplyResult:
        validate_fraud_event(event)
        score = _score(event.occurred_at)
        payload = event.payload
        user_id = payload.user_id
        device_id = (
            payload.device_id if isinstance(payload, AccountCreatedPayload) else None
        )
        result = self.client.eval(
            _APPLY,
            5,
            self._state_key,
            self._identity_key,
            self._key("payments", user_id),
            self._key("failures", user_id),
            self._key("device", device_id or ""),
            str(event.event_id),
            canonical_event_identity(event),
            event.event_type,
            str(score),
            "1" if device_id is not None else "0",
            user_id,
        )
        if result == "CONFLICT":
            raise EventIdentityConflict(f"conflicting event_id: {event.event_id}")
        if result in ("UNINITIALIZED", "INVALID_STATE"):
            raise ProjectionUnavailable(f"projection is {result}")
        return ApplyResult(result)

    def features_for(
        self, *, user_id: str, device_id: str | None, as_of: Timestamp
    ) -> OnlineFeatureSnapshot:
        query = OnlineFeatureSnapshot(
            user_id=user_id,
            device_id=device_id,
            as_of=as_of,
            payments_10m=0,
            failed_payments_1h=0,
            accounts_on_device=None if device_id is None else 0,
        )
        end = _score(query.as_of)
        payment_start = _score(query.as_of - timedelta(minutes=10))
        failure_start = _score(query.as_of - timedelta(hours=1))
        result = self.client.eval(
            _QUERY,
            4,
            self._state_key,
            self._key("payments", query.user_id),
            self._key("failures", query.user_id),
            self._key("device", query.device_id or ""),
            str(payment_start),
            str(failure_start),
            str(end),
            "1" if query.device_id is not None else "0",
        )
        if result[0] != "READY":
            raise ProjectionUnavailable(f"projection is {result[0]}")
        return query.model_copy(
            update={
                "payments_10m": int(result[1]),
                "failed_payments_1h": int(result[2]),
                "accounts_on_device": None if device_id is None else int(result[3]),
            }
        )
