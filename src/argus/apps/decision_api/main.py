"""Decision API entry point."""

import hashlib
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

from argus.apps.decision_api.service import (
    DecisionResult,
    DecisionService,
    IdempotencyKeyReused,
)
from argus.domain.models import Decision, DecisionContext
from argus.persistence import schema as s
from argus.persistence.database import create_engine
from argus.persistence.repository import PersistenceConflict

logger = logging.getLogger(__name__)


class Liveness(BaseModel):
    status: str
    service: str


class PaymentDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: DecisionContext


class DecisionResponse(BaseModel):
    decision: Decision
    replayed: bool


def error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status
    )


def key_reference(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:12]


@asynccontextmanager
async def lifespan(app: FastAPI):
    url = os.environ.get("ARGUS_DATABASE_URL")
    if not url:
        raise RuntimeError("ARGUS_DATABASE_URL is required for Decision API")
    engine = create_engine(url)
    app.state.engine = engine
    app.state.service = DecisionService(engine)
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(title="Argus Decision API", lifespan=lifespan)


@app.get("/health/live", response_model=Liveness)
def live() -> Liveness:
    return Liveness(status="ok", service="decision-api")


@app.get("/health/ready")
def ready(request: Request):
    try:
        with request.app.state.engine.connect() as connection:
            # Resolve columns against the actual schema, without depending on Alembic.
            for table in (
                s.users,
                s.devices,
                s.transactions,
                s.payments,
                s.decisions,
                s.decision_idempotency,
                s.reasons,
                s.decision_devices,
                s.signals,
                s.evaluations,
                s.evidence,
            ):
                connection.execute(select(table).limit(0))
    except DBAPIError as exc:
        logger.warning(
            "DATABASE_UNAVAILABLE readiness error_type=%s", type(exc).__name__
        )
        return error(
            "DATABASE_UNAVAILABLE", "PostgreSQL decision schema unavailable", 503
        )
    return {"status": "ready", "service": "decision-api"}


@app.post("/v1/decisions/payment", response_model=DecisionResponse)
def decide_payment(
    request: Request,
    body: PaymentDecisionRequest,
    idempotency_key: str = Header(min_length=1, max_length=255),
) -> DecisionResponse | JSONResponse:
    if not idempotency_key.strip():
        return error(
            "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must not be blank", 422
        )
    reference = key_reference(idempotency_key)
    try:
        result: DecisionResult = request.app.state.service.decide(
            body.context, idempotency_key
        )
    except IdempotencyKeyReused:
        logger.info("IDEMPOTENCY_KEY_REUSED key_ref=%s", reference)
        return error("IDEMPOTENCY_KEY_REUSED", "Key belongs to another request", 409)
    except PersistenceConflict:
        logger.info("AUTHORITATIVE_FACT_CONFLICT key_ref=%s", reference)
        return error("AUTHORITATIVE_FACT_CONFLICT", "Conflicting recorded fact", 409)
    except (OperationalError, InterfaceError) as exc:
        logger.warning(
            "DATABASE_UNAVAILABLE key_ref=%s error_type=%s",
            reference,
            type(exc).__name__,
        )
        return error(
            "DATABASE_UNAVAILABLE", "Decision service is temporarily unavailable", 503
        )
    except DBAPIError as exc:
        if exc.connection_invalidated:
            logger.warning("DATABASE_UNAVAILABLE key_ref=%s", reference)
            return error(
                "DATABASE_UNAVAILABLE",
                "Decision service is temporarily unavailable",
                503,
            )
        logger.error(
            "Unexpected database error key_ref=%s type=%s",
            reference,
            type(exc).__name__,
        )
        return error("INTERNAL_ERROR", "Decision could not be recorded", 500)
    except Exception:
        logger.exception("Unexpected decision failure key_ref=%s", reference)
        return error("INTERNAL_ERROR", "Decision could not be recorded", 500)
    return DecisionResponse(decision=result.decision, replayed=result.replayed)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("ARGUS_HOST", "127.0.0.1"),
        port=int(os.getenv("ARGUS_PORT", "8001")),
        log_level=os.getenv("ARGUS_LOG_LEVEL", "info"),
    )
