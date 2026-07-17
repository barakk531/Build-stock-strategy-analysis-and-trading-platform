"""Health endpoint against a real database.

Runs only when DATABASE_URL is set (e.g. Postgres from `docker compose up db`);
skips cleanly otherwise so the unit suite never needs infrastructure.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; start Postgres and set it to run integration tests",
)


def test_health_reports_database_ok(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
