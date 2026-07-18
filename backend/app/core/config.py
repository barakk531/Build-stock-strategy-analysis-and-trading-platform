"""Application settings, loaded from environment variables and the repo-root .env.

Environment variables always take precedence over the .env file, so Docker
Compose can inject container-specific values (e.g. DATABASE_URL pointing at the
`db` service) without touching the file.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three levels above app/.
# Inside the Docker image this resolves to /.env, which doesn't exist — env
# vars from compose are the only source there.
_REPO_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT_ENV if _REPO_ROOT_ENV.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Stock Strategy Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://stocks:stocks@localhost:5432/stocks"
    db_connect_timeout_seconds: int = 3

    # Comma-separated; parsed by cors_origins below.
    backend_cors_origins: str = "http://localhost:5173"

    scheduler_enabled: bool = True
    # All market scheduling uses this zone — never the server's local date.
    market_timezone: str = "America/New_York"

    # --- Market data (Phase 2) ---
    # Current S&P 500 constituents. Fetched via curl_cffi (BoringSSL) so it works
    # behind Avast's TLS interception on this machine, where stdlib ssl fails.
    sp500_source_url: str = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    price_history_years: int = 20
    # Re-fetch a small trailing window on incremental sync to pick up revisions.
    price_sync_overlap_days: int = 5
    # yfinance batch download size and retry policy.
    yahoo_batch_size: int = 40
    yahoo_max_retries: int = 3
    yahoo_backoff_seconds: float = 2.0

    # Telegram alerts (Phase 5)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_alerts_enabled: bool = False
    # both | buy | sell
    telegram_alert_types: str = "both"
    telegram_min_market_cap: int | None = None
    # Base URL used for chart links inside alerts.
    frontend_base_url: str = "http://localhost:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
