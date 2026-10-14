"""Production-compatible event construction shared by simulation scenarios."""

import json
from datetime import datetime
from uuid import UUID, uuid5

from argus.events.envelope import EventEnvelope
from argus.events.fraud import FraudPayload, validate_fraud_event
from argus.simulation.kernel import SimulationManifest

_EVENT_NAMESPACE = UUID("06a87c42-06f4-50f2-a352-a608657596af")
_PRODUCER = "argus-simulator-v1"


def scenario_identity(
    manifest: SimulationManifest, scenario_name: str, config_json: str
) -> str:
    return json.dumps(
        {
            "kernel": json.loads(manifest.to_json()),
            scenario_name: json.loads(config_json),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def simulation_event(
    run_identity: str,
    event_type: str,
    subject_id: str,
    trace_id: str,
    payload: FraudPayload,
    at: datetime,
) -> EventEnvelope[FraudPayload]:
    event = EventEnvelope[FraudPayload](
        event_id=uuid5(_EVENT_NAMESPACE, f"{run_identity}:{event_type}:{subject_id}"),
        event_type=event_type,
        event_version=1,
        occurred_at=at,
        produced_at=at,
        producer=_PRODUCER,
        trace_id=trace_id,
        subject_id=subject_id,
        payload=payload,
    )
    validate_fraud_event(event)
    return event
