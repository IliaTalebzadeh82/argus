"""Decision API entry point."""

import os

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel


class Liveness(BaseModel):
    status: str
    service: str


app = FastAPI(title="Argus Decision API")


@app.get("/health/live", response_model=Liveness)
def live() -> Liveness:
    return Liveness(status="ok", service="decision-api")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("ARGUS_HOST", "127.0.0.1"),
        port=int(os.getenv("ARGUS_PORT", "8001")),
        log_level=os.getenv("ARGUS_LOG_LEVEL", "info"),
    )
