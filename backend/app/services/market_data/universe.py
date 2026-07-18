"""S&P 500 universe synchronization.

Fetches the current constituent list, upserts each company, and marks removed
constituents inactive (never deletes). The fetch uses curl_cffi (BoringSSL) so
it works behind Avast's TLS interception on this machine — stdlib ssl would
fail there even with the Windows-store bundle (see certs.py).

v1 limitation (documented in docs/backtesting-assumptions.md): this is the
CURRENT membership only — historical membership is future work, so backtests
carry survivorship bias.
"""

from __future__ import annotations

import logging
from datetime import date
from io import StringIO

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories import stock_repository
from app.services.market_data import certs

logger = logging.getLogger(__name__)


class UniverseError(Exception):
    """Raised when the constituent list cannot be fetched or parsed."""


def to_yahoo_symbol(symbol: str) -> str:
    """Yahoo uses '-' where index providers use '.' (BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def _fetch_constituents_html(url: str) -> str:
    certs.trust_windows_roots()
    from curl_cffi import requests as curl_requests  # lazy: import cost + TLS env

    response = curl_requests.get(url, impersonate="chrome", timeout=30)
    if response.status_code != 200:
        raise UniverseError(f"Constituent source returned HTTP {response.status_code}")
    return response.text


def parse_constituents(html: str) -> list[dict]:
    """Parse the constituents table into upsert rows.

    Wikipedia's first table carries Symbol / Security / GICS Sector /
    GICS Sub-Industry / Date added. Column names are matched loosely so minor
    page edits don't break the sync.
    """
    try:
        # flavor pinned to lxml: without it, a table-less page makes pandas try
        # the html5lib fallback and raise ImportError instead of ValueError.
        tables = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise UniverseError("No constituents table found in source page") from exc
    frame = None
    for candidate in tables:
        cols = [str(c).lower() for c in candidate.columns]
        if any("symbol" in c for c in cols) and any("security" in c for c in cols):
            frame = candidate
            break
    if frame is None:
        raise UniverseError("No constituents table found in source page")

    def col(*needles: str) -> str | None:
        for c in frame.columns:
            name = str(c).lower()
            if all(n in name for n in needles):
                return c
        return None

    symbol_col = col("symbol")
    name_col = col("security")
    sector_col = col("gics", "sector")
    industry_col = col("sub-industry") or col("sub industry")
    added_col = col("date", "added")

    rows: list[dict] = []
    seen: set[str] = set()
    for _, row in frame.iterrows():
        raw_symbol = str(row[symbol_col]).strip().upper()
        if not raw_symbol or raw_symbol == "NAN" or raw_symbol in seen:
            continue
        seen.add(raw_symbol)

        added: date | None = None
        if added_col is not None and pd.notna(row[added_col]):
            parsed = pd.to_datetime(str(row[added_col]), errors="coerce")
            if pd.notna(parsed):
                added = parsed.date()

        rows.append(
            {
                "symbol": raw_symbol,
                "yahoo_symbol": to_yahoo_symbol(raw_symbol),
                "company_name": str(row[name_col]).strip() if name_col else None,
                "sector": str(row[sector_col]).strip() if sector_col else None,
                "industry": str(row[industry_col]).strip() if industry_col else None,
                "date_added_to_index": added,
            }
        )

    if len(rows) < 400:  # sanity: the S&P 500 has ~503 tickers
        raise UniverseError(f"Parsed only {len(rows)} constituents — source layout changed?")
    return rows


def sync_universe(db: Session) -> dict:
    """Fetch + upsert the current S&P 500 membership. Idempotent."""
    settings = get_settings()
    html = _fetch_constituents_html(settings.sp500_source_url)
    rows = parse_constituents(html)
    upserted, deactivated = stock_repository.upsert_constituents(db, rows)
    logger.info("universe sync upserted=%d deactivated=%d", upserted, deactivated)
    return {"constituents": upserted, "deactivated": deactivated}
