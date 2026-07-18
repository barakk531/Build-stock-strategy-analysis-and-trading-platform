"""Data access for signals: duplicate-proof inserts and filtered listings."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.signal import Signal

_INSERT_CHUNK = 500


def insert_signals(db: Session, rows: list[dict]) -> int:
    """Insert signal rows; duplicates (per uq_signals_dedupe) are skipped.
    Returns the number actually inserted (rowcount excludes conflicts)."""
    if not rows:
        return 0
    inserted = 0
    for start in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[start : start + _INSERT_CHUNK]
        stmt = (
            pg_insert(Signal)
            .values(chunk)
            .on_conflict_do_nothing(constraint="uq_signals_dedupe")
            # RETURNING yields only the rows actually inserted, so the count is
            # exact (rowcount is -1 on the insertmanyvalues path).
            .returning(Signal.id)
        )
        inserted += len(db.execute(stmt).scalars().all())
    db.commit()
    return inserted


def list_signals(
    db: Session,
    *,
    stock_id: int | None = None,
    strategy_id: int | None = None,
    signal_type: str | None = None,
    since: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Signal]:
    query = select(Signal)
    if stock_id is not None:
        query = query.where(Signal.stock_id == stock_id)
    if strategy_id is not None:
        query = query.where(Signal.strategy_id == strategy_id)
    if signal_type:
        query = query.where(Signal.signal_type == signal_type.upper())
    if since:
        query = query.where(Signal.trade_date >= since)
    query = query.order_by(Signal.trade_date.desc(), Signal.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(query))


def latest_for_stock(db: Session, stock_id: int, strategy_id: int | None = None) -> Signal | None:
    query = select(Signal).where(Signal.stock_id == stock_id)
    if strategy_id is not None:
        query = query.where(Signal.strategy_id == strategy_id)
    return db.scalar(query.order_by(Signal.trade_date.desc(), Signal.id.desc()).limit(1))
