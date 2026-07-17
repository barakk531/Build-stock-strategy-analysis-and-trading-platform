"""Health endpoint: response shape, db-up and db-down behavior."""

from contextlib import contextmanager
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from app.db import session


def _engine_that_works():
    engine = MagicMock()
    conn = MagicMock()

    @contextmanager
    def connect():
        yield conn

    engine.connect = connect
    return engine


def _engine_that_fails():
    engine = MagicMock()
    engine.connect.side_effect = OperationalError("SELECT 1", None, Exception("db down"))
    return engine


def test_health_ok_when_db_reachable(client, monkeypatch):
    monkeypatch.setattr(session, "engine", _engine_that_works())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["environment"] == "test"
    assert body["version"]
    assert body["timestamp"]


def test_health_degraded_when_db_down(client, monkeypatch):
    monkeypatch.setattr(session, "engine", _engine_that_fails())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"


def test_openapi_schema_available(client):
    assert client.get("/api/v1/openapi.json").status_code == 200
