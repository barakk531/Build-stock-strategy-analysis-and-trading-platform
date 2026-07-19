"""Yahoo Finance daily-history downloader.

Wraps yfinance with retry + exponential backoff and normalizes each ticker's
frame into upsert-ready rows. auto_adjust=False keeps BOTH the raw close and
the adjusted close ("Adj Close"), since indicators use adjusted prices while
the raw close stays available for display — documented in
docs/data-source-limitations.md.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import date

import pandas as pd

from app.core.config import get_settings
from app.services.market_data import certs

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when Yahoo returns nothing usable after retries."""


def _clean_number(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def frame_to_rows(frame: pd.DataFrame) -> list[dict]:
    """Convert one ticker's yfinance frame into daily_prices upsert rows.

    Skips rows without a close (Yahoo emits all-NaN rows for halts/holidays).
    Validates that prices are positive and volume non-negative.
    """
    rows: list[dict] = []
    for index, row in frame.iterrows():
        trade_date = index.date() if hasattr(index, "date") else index
        close = _clean_number(row.get("Close"))
        if close is None or close <= 0:
            continue
        adj = _clean_number(row.get("Adj Close"))
        volume = _clean_number(row.get("Volume"))
        if volume is not None and volume < 0:
            continue
        rows.append(
            {
                "trade_date": trade_date,
                "open": _clean_number(row.get("Open")),
                "high": _clean_number(row.get("High")),
                "low": _clean_number(row.get("Low")),
                "close": close,
                "adjusted_close": adj if adj is not None and adj > 0 else close,
                "volume": int(volume) if volume is not None else None,
                "dividend": _clean_number(row.get("Dividends")) or 0,
                "stock_split": _clean_number(row.get("Stock Splits")) or 0,
            }
        )
    return rows


def download_history(
    yahoo_symbols: list[str],
    *,
    start: date | None = None,
    period_years: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Batch-download daily history. Returns {yahoo_symbol: frame}; symbols
    with no data are omitted (and logged) rather than failing the batch.
    """
    if not yahoo_symbols:
        return {}
    settings = get_settings()
    certs.trust_windows_roots()
    import yfinance as yf  # lazy: reads TLS env at session creation

    kwargs: dict = {
        "interval": "1d",
        "auto_adjust": False,
        "actions": True,
        "progress": False,
        "group_by": "ticker",
        "threads": True,
    }
    if start is not None:
        kwargs["start"] = start.isoformat()
    else:
        kwargs["period"] = f"{period_years or settings.price_history_years}y"

    last_error: Exception | None = None
    for attempt in range(settings.yahoo_max_retries):
        try:
            data = yf.download(yahoo_symbols, **kwargs)
            break
        except Exception as exc:  # yfinance raises assorted network errors
            last_error = exc
            wait = settings.yahoo_backoff_seconds * (2**attempt)
            logger.warning(
                "yahoo download retry attempt=%d wait=%.1fs error=%s",
                attempt + 1,
                wait,
                exc.__class__.__name__,
            )
            time.sleep(wait)
    else:
        raise DownloadError(f"Yahoo download failed after retries: {last_error}")

    if data is None or data.empty:
        logger.warning("yahoo download empty symbols=%d", len(yahoo_symbols))
        return {}

    out: dict[str, pd.DataFrame] = {}
    if len(yahoo_symbols) == 1:
        # group_by="ticker" nests columns under the symbol even for a single
        # ticker — flatten so frame_to_rows sees plain OHLCV column names.
        frame = data
        if isinstance(frame.columns, pd.MultiIndex):
            try:
                frame = frame[yahoo_symbols[0]]
            except KeyError:
                logger.warning("yahoo no data symbol=%s", yahoo_symbols[0])
                return {}
        frame = frame.dropna(how="all")
        if not frame.empty:
            out[yahoo_symbols[0]] = frame
        return out

    for symbol in yahoo_symbols:
        try:
            frame = data[symbol].dropna(how="all")
        except KeyError:
            logger.warning("yahoo no data symbol=%s", symbol)
            continue
        if not frame.empty:
            out[symbol] = frame
    return out


def fetch_metadata(yahoo_symbol: str) -> dict:
    """Fetch company metadata (market cap, exchange, ...) for one symbol.

    Best-effort: returns {} when Yahoo has nothing, so callers can skip.
    """
    certs.trust_windows_roots()
    import yfinance as yf

    try:
        info = yf.Ticker(yahoo_symbol).info or {}
    except Exception as exc:
        logger.warning("yahoo metadata failed symbol=%s error=%s", yahoo_symbol, exc)
        return {}

    return {
        "company_name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "exchange": info.get("fullExchangeName") or info.get("exchange"),
        "currency": info.get("currency"),
        "market_cap": info.get("marketCap"),
    }
