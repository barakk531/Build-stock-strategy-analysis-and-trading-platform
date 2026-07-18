"""Price-sync orchestration: initial 20-year backfill and incremental refresh.

Design constraints from the spec:
- Resumable: each stock's rows commit independently; last_price_sync records
  progress, so a crash mid-run resumes where it left off.
- Idempotent: upserts never duplicate (unique stock_id+trade_date).
- Incremental: only missing dates are fetched, plus a small overlap window to
  pick up Yahoo's revised rows.
- Failures are logged per symbol and never abort the whole run.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories import price_repository, stock_repository
from app.services.market_data import downloader

logger = logging.getLogger(__name__)


def _batched(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def sync_prices(
    db: Session,
    *,
    symbols: list[str] | None = None,
    full: bool = False,
) -> dict:
    """Download and store daily history for active stocks.

    - full=True (or no existing rows for a stock): backfill `price_history_years`.
    - otherwise: fetch from (latest stored date - overlap) forward.

    Returns a summary dict with per-symbol failures.
    """
    settings = get_settings()
    stocks = stock_repository.list_active_for_sync(db)
    if symbols:
        wanted = {s.upper() for s in symbols}
        stocks = [s for s in stocks if s.symbol in wanted]
    if not stocks:
        return {"synced": 0, "rows": 0, "failed": []}

    today = date.today()
    overlap = timedelta(days=settings.price_sync_overlap_days)

    # Split stocks into "backfill" (no data yet, or full requested) and
    # "incremental" groups; incremental stocks share a common start date so
    # they can batch together.
    backfill: list = []
    incremental: list = []
    incremental_start: date | None = None
    for stock in stocks:
        latest = None if full else price_repository.latest_trade_date(db, stock.id)
        if latest is None:
            backfill.append(stock)
        else:
            start = latest - overlap
            incremental.append((stock, start))
            incremental_start = min(incremental_start or start, start)

    rows_written = 0
    synced = 0
    failed: list[dict] = []

    def _store(stock, frame) -> None:
        nonlocal rows_written, synced
        rows = downloader.frame_to_rows(frame)
        if not rows:
            failed.append({"symbol": stock.symbol, "reason": "no rows after cleaning"})
            return
        rows_written += price_repository.upsert_prices(db, stock.id, rows)
        stock_repository.mark_price_sync(db, stock)
        synced += 1

    def _run_group(group: list, *, start: date | None, label: str) -> None:
        by_yahoo = {stock.yahoo_symbol: stock for stock in group}
        for batch in _batched(list(by_yahoo.keys()), settings.yahoo_batch_size):
            try:
                frames = downloader.download_history(batch, start=start)
            except downloader.DownloadError as exc:
                for symbol in batch:
                    failed.append({"symbol": by_yahoo[symbol].symbol, "reason": str(exc)})
                continue
            for symbol in batch:
                stock = by_yahoo[symbol]
                frame = frames.get(symbol)
                if frame is None:
                    failed.append({"symbol": stock.symbol, "reason": "no data returned"})
                    continue
                try:
                    _store(stock, frame)
                except Exception as exc:  # keep the run alive; log the symbol
                    logger.exception("price store failed symbol=%s", stock.symbol)
                    failed.append({"symbol": stock.symbol, "reason": str(exc)})
        logger.info(
            "price sync group=%s stocks=%d synced=%d failed=%d",
            label,
            len(group),
            synced,
            len(failed),
        )

    if backfill:
        _run_group(backfill, start=None, label="backfill")
    if incremental:
        # A shared conservative start date keeps batching simple; the upsert
        # makes re-writing a few extra overlap days harmless.
        stocks_only = [stock for stock, _ in incremental]
        _run_group(stocks_only, start=incremental_start, label="incremental")

    return {
        "synced": synced,
        "rows": rows_written,
        "failed": failed,
        "as_of": today.isoformat(),
    }


def refresh_metadata(db: Session, *, symbols: list[str] | None = None, limit: int = 60) -> dict:
    """Refresh company metadata (market cap, exchange, ...), oldest-first.

    Metadata is one HTTP call per symbol, so runs are capped by `limit` and the
    weekly job cycles through the universe across runs.
    """
    stocks = stock_repository.list_active_for_sync(db)
    if symbols:
        wanted = {s.upper() for s in symbols}
        stocks = [s for s in stocks if s.symbol in wanted]
    stocks.sort(key=lambda s: (s.last_metadata_update or s.created_at))
    stocks = stocks[:limit]

    updated = 0
    failed: list[dict] = []
    for stock in stocks:
        meta = downloader.fetch_metadata(stock.yahoo_symbol)
        if not meta or all(value is None for value in meta.values()):
            failed.append({"symbol": stock.symbol, "reason": "no metadata"})
            continue
        stock_repository.update_metadata(db, stock, meta)
        updated += 1

    logger.info("metadata refresh updated=%d failed=%d", updated, len(failed))
    return {"updated": updated, "failed": failed}
