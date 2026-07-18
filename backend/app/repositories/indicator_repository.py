"""Data access for daily_indicators (default-parameter values)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.daily_indicator import DailyIndicator

_UPSERT_CHUNK = 1000

_UPDATABLE = ("sma_20", "sma_50", "sma_150", "average_volume", "volume_ratio", "sma_150_slope")


def upsert_indicators(db: Session, stock_id: int, rows: list[dict]) -> int:
    """Idempotent write of indicator rows (unique stock_id+trade_date)."""
    if not rows:
        return 0
    payload = [{"stock_id": stock_id, **row} for row in rows]
    for start in range(0, len(payload), _UPSERT_CHUNK):
        chunk = payload[start : start + _UPSERT_CHUNK]
        stmt = pg_insert(DailyIndicator).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_daily_indicators_stock_date",
            set_={col: getattr(stmt.excluded, col) for col in _UPDATABLE}
            | {"updated_at": func.now()},
        )
        db.execute(stmt)
    db.commit()
    return len(payload)


def get_indicators(
    db: Session,
    stock_id: int,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> list[DailyIndicator]:
    query = select(DailyIndicator).where(DailyIndicator.stock_id == stock_id)
    if start:
        query = query.where(DailyIndicator.trade_date >= start)
    if end:
        query = query.where(DailyIndicator.trade_date <= end)
    query = query.order_by(DailyIndicator.trade_date.desc())
    if limit:
        query = query.limit(limit)
    rows = list(db.scalars(query))
    rows.reverse()
    return rows


def latest_for_stock(db: Session, stock_id: int) -> DailyIndicator | None:
    return db.scalar(
        select(DailyIndicator)
        .where(DailyIndicator.stock_id == stock_id)
        .order_by(DailyIndicator.trade_date.desc())
        .limit(1)
    )
