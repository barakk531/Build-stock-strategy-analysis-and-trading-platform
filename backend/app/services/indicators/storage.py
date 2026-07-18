"""Compute default-parameter indicators from stored prices and persist them."""

from __future__ import annotations

import logging
import math

from sqlalchemy.orm import Session

from app.repositories import indicator_repository, price_repository, stock_repository
from app.services.indicators import calculator as calc

logger = logging.getLogger(__name__)


def _clean(value) -> float | None:
    if value is None:
        return None
    number = float(value)
    return None if (math.isnan(number) or math.isinf(number)) else number


def recalculate_for_stock(db: Session, stock) -> int:
    """Recompute and upsert the full default-indicator series for one stock."""
    prices = price_repository.get_prices(db, stock.id)
    if len(prices) < 2:
        return 0
    frame = calc.prices_to_frame(prices)
    indicators = calc.compute_indicators(frame)

    rows = []
    for trade_date, row in indicators.iterrows():
        rows.append(
            {
                "trade_date": trade_date,
                "sma_20": _clean(row[calc.SMA_SHORT]),
                "sma_50": _clean(row[calc.SMA_MEDIUM]),
                "sma_150": _clean(row[calc.SMA_LONG]),
                "average_volume": _clean(row[calc.AVERAGE_VOLUME]),
                "volume_ratio": _clean(row[calc.VOLUME_RATIO]),
                "sma_150_slope": _clean(row[calc.SMA_LONG_SLOPE]),
            }
        )
    return indicator_repository.upsert_indicators(db, stock.id, rows)


def recalculate(db: Session, *, symbols: list[str] | None = None) -> dict:
    """Recompute default indicators for active stocks (all or a subset)."""
    stocks = stock_repository.list_active_for_sync(db)
    if symbols:
        wanted = {s.upper() for s in symbols}
        stocks = [s for s in stocks if s.symbol in wanted]

    updated = 0
    rows_written = 0
    failed: list[dict] = []
    for stock in stocks:
        try:
            written = recalculate_for_stock(db, stock)
        except Exception as exc:  # keep the run alive
            logger.exception("indicator recalc failed symbol=%s", stock.symbol)
            failed.append({"symbol": stock.symbol, "reason": str(exc)})
            continue
        if written:
            updated += 1
            rows_written += written
    logger.info("indicator recalc stocks=%d rows=%d failed=%d", updated, rows_written, len(failed))
    return {"stocks": updated, "rows": rows_written, "failed": failed}
