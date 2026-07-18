"""Data access for daily prices: idempotent upserts and range queries."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.daily_price import DailyPrice

_UPSERT_CHUNK = 1000

_UPDATABLE = (
    "open",
    "high",
    "low",
    "close",
    "adjusted_close",
    "volume",
    "dividend",
    "stock_split",
)


def upsert_prices(db: Session, stock_id: int, rows: list[dict]) -> int:
    """Insert-or-update daily rows for one stock. Re-running never duplicates
    (unique stock_id+trade_date); revised Yahoo data overwrites the old row.

    Each row needs trade_date plus any of open/high/low/close/adjusted_close/
    volume/dividend/stock_split. Returns the number of rows written.
    """
    if not rows:
        return 0

    payload = [{"stock_id": stock_id, **row} for row in rows]
    for start in range(0, len(payload), _UPSERT_CHUNK):
        chunk = payload[start : start + _UPSERT_CHUNK]
        stmt = pg_insert(DailyPrice).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_daily_prices_stock_date",
            set_={col: getattr(stmt.excluded, col) for col in _UPDATABLE}
            | {"updated_at": func.now()},
        )
        db.execute(stmt)
    db.commit()
    return len(payload)


def latest_trade_date(db: Session, stock_id: int) -> date | None:
    return db.scalar(
        select(func.max(DailyPrice.trade_date)).where(DailyPrice.stock_id == stock_id)
    )


def get_prices(
    db: Session,
    stock_id: int,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> list[DailyPrice]:
    query = select(DailyPrice).where(DailyPrice.stock_id == stock_id)
    if start:
        query = query.where(DailyPrice.trade_date >= start)
    if end:
        query = query.where(DailyPrice.trade_date <= end)
    query = query.order_by(DailyPrice.trade_date.desc())
    if limit:
        query = query.limit(limit)
    rows = list(db.scalars(query))
    rows.reverse()  # chronological for charting/indicators
    return rows


def count_for_stock(db: Session, stock_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(DailyPrice).where(DailyPrice.stock_id == stock_id)
    ) or 0
