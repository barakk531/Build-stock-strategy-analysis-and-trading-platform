"""Market-clock date helpers (spec §3: never rely on the server's local date)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def market_today() -> date:
    """Today in the market timezone (America/New_York), not server-local."""
    return datetime.now(ZoneInfo(get_settings().market_timezone)).date()
