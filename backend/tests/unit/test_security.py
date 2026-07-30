"""API-key auth and secret sanitization (spec §20). No database needed —
/admin/jobs and /health answer without one."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import require_admin
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def with_key(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-secret-key")
    get_settings.cache_clear()
    yield "test-secret-key"
    get_settings.cache_clear()


@pytest.fixture()
def without_key(monkeypatch):
    # Empty env var (not deletion) so a key in a local .env can't leak in.
    monkeypatch.setenv("ADMIN_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_guarded_endpoint_open_when_auth_disabled(client, without_key):
    assert client.get("/api/v1/admin/jobs").status_code == 200


def test_guarded_endpoint_requires_key_when_configured(client, with_key):
    assert client.get("/api/v1/admin/jobs").status_code == 401
    wrong = client.get("/api/v1/admin/jobs", headers={"X-API-Key": "nope"})
    assert wrong.status_code == 401
    ok = client.get("/api/v1/admin/jobs", headers={"X-API-Key": with_key})
    assert ok.status_code == 200


def test_mutating_routers_are_guarded(client, with_key):
    # Trading-state routers are key-protected as a whole.
    assert client.get("/api/v1/backtests").status_code == 401
    assert client.get("/api/v1/paper-accounts").status_code == 401
    assert client.get("/api/v1/competitions").status_code == 401
    # Read-only market data stays public.
    assert client.get("/api/v1/health").status_code == 200


def test_health_reports_auth_mode(client, with_key):
    assert client.get("/api/v1/health").json()["auth_required"] is True


def test_health_reports_auth_disabled(client, without_key):
    assert client.get("/api/v1/health").json()["auth_required"] is False


def test_non_ascii_configured_key_returns_401_not_500(client, monkeypatch):
    # secrets.compare_digest(str, str) raises TypeError on non-ASCII input; the
    # fix encodes to bytes first so a non-ASCII *configured* key degrades to a
    # normal 401 instead of a 500. httpx can only transmit an ASCII header, so
    # the non-ASCII side under test here is the configured key.
    monkeypatch.setenv("ADMIN_API_KEY", "clé-non-ascii-héllo")
    get_settings.cache_clear()
    wrong = client.get("/api/v1/admin/jobs", headers={"X-API-Key": "wrong"})
    assert wrong.status_code == 401
    get_settings.cache_clear()


def test_require_admin_compares_non_ascii_keys_safely(monkeypatch):
    # The incoming-key side can't be tested over httpx (it refuses to encode a
    # non-ASCII header value), so exercise the dependency directly: a non-ASCII
    # wrong key must 401 without raising TypeError, and the exact non-ASCII
    # match must pass (require_admin returns None on success).
    monkeypatch.setenv("ADMIN_API_KEY", "clé-non-ascii-héllo")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        require_admin("clé-différente")
    assert exc.value.status_code == 401
    assert require_admin("clé-non-ascii-héllo") is None
    get_settings.cache_clear()


def test_config_masks_secrets(client, with_key, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567890:AAAAAAAAsecretsecretBBBB")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    get_settings.cache_clear()
    body = client.get("/api/v1/admin/config", headers={"X-API-Key": with_key}).json()
    dumped = str(body)
    assert "secretsecret" not in dumped
    assert "test-secret-key" not in dumped
    assert body["telegram"]["bot_token"].startswith("1234")
    assert "…" in body["telegram"]["bot_token"]
    assert body["auth_required"] is True
    get_settings.cache_clear()
