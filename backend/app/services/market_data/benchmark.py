"""Benchmark series access, shared by backtests and paper accounts.

The benchmark is a normal tracked symbol (auto-added as non-S&P so universe
syncs never deactivate it, auto-synced when stale) whose adjusted closes are
returned as a pandas Series. Any failure — network down, unknown symbol —
degrades to (None, note): a benchmark must never sink the caller.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.repositories import price_repository, stock_repository

logger = logging.getLogger(__name__)

KNOWN_NAMES = {
    "^GSPC": "S&P 500 Index",
    "^NDX": "Nasdaq 100 Index",
    "^DJI": "Dow Jones Industrial Average",
    "SPY": "SPDR S&P 500 ETF",
}


def get_series(
    db: Session, symbol: str | None, start: date, end: date
) -> tuple[pd.Series | None, str | None]:
    """(adjusted-close series in [start, end], note) — series None on failure."""
    if not symbol:
        return None, None
    try:
        stock = stock_repository.ensure_stock(
            db, symbol, company_name=KNOWN_NAMES.get(symbol.upper()), is_sp500=False
        )
        latest = price_repository.latest_trade_date(db, stock.id)
        needed_through = min(end, date.today() - timedelta(days=1))
        if latest is None or latest < needed_through - timedelta(days=5):
            from app.services.market_data import sync as sync_service

            sync_service.sync_prices(db, symbols=[stock.symbol], full=latest is None)
        prices = price_repository.get_prices(db, stock.id, start=start, end=end)
        values = {
            p.trade_date: float(p.adjusted_close) for p in prices if p.adjusted_close is not None
        }
        if len(values) < 2:
            return None, f"benchmark {symbol}: no data in range"
        return pd.Series(values).sort_index(), None
    except Exception as exc:  # optional feature — never fail the caller
        logger.warning("benchmark unavailable symbol=%s error=%s", symbol, exc)
        return None, f"benchmark {symbol} unavailable: {exc}"
