"""The two process boundaries expose their own liveness identity."""

from fastapi.testclient import TestClient

from argus.apps.decision_api.main import app as decision_app
from argus.apps.investigator_api.main import app as investigator_app


def test_decision_liveness(monkeypatch) -> None:
    monkeypatch.setenv(
        "ARGUS_DATABASE_URL", "postgresql+psycopg://argus:argus@localhost/argus"
    )
    monkeypatch.setenv("ARGUS_REDIS_URL", "redis://localhost:6379/0")
    with TestClient(decision_app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "decision-api"}


def test_investigator_liveness() -> None:
    with TestClient(investigator_app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "investigator-api"}
