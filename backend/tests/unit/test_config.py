"""Settings parsing from environment variables."""

from app.core.config import Settings


def test_defaults(monkeypatch):
    for var in ("DATABASE_URL", "BACKEND_CORS_ORIGINS", "LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.market_timezone == "America/New_York"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@db:5432/other")
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://a.example, http://b.example,")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/other"
    assert settings.cors_origins == ["http://a.example", "http://b.example"]
