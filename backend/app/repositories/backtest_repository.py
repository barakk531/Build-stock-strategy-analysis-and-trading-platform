"""Data access for backtest runs, trades, and skipped signals."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.backtest import BacktestRun, BacktestSkip, BacktestTrade

_INSERT_CHUNK = 1000


def get_run(db: Session, run_id: int) -> BacktestRun | None:
    return db.get(BacktestRun, run_id)


def list_runs(db: Session, *, limit: int = 50, offset: int = 0) -> tuple[list[BacktestRun], int]:
    total = db.scalar(select(func.count()).select_from(BacktestRun)) or 0
    rows = db.scalars(
        select(BacktestRun)
        .order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def delete_run(db: Session, run: BacktestRun) -> None:
    db.delete(run)  # trades/skips cascade at the database level
    db.commit()


def bulk_insert_trades(db: Session, rows: list[dict]) -> int:
    for start in range(0, len(rows), _INSERT_CHUNK):
        db.execute(BacktestTrade.__table__.insert(), rows[start : start + _INSERT_CHUNK])
    return len(rows)


def bulk_insert_skips(db: Session, rows: list[dict]) -> int:
    for start in range(0, len(rows), _INSERT_CHUNK):
        db.execute(BacktestSkip.__table__.insert(), rows[start : start + _INSERT_CHUNK])
    return len(rows)


def list_trades(
    db: Session,
    run_id: int,
    *,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[BacktestTrade], int]:
    query = select(BacktestTrade).where(BacktestTrade.backtest_run_id == run_id)
    if status:
        query = query.where(BacktestTrade.status == status.upper())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(BacktestTrade.entry_date, BacktestTrade.symbol).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def list_skips(
    db: Session,
    run_id: int,
    *,
    reason: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[BacktestSkip], int]:
    query = select(BacktestSkip).where(BacktestSkip.backtest_run_id == run_id)
    if reason:
        query = query.where(BacktestSkip.reason == reason)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(BacktestSkip.signal_date, BacktestSkip.symbol).limit(limit).offset(offset)
    ).all()
    return list(rows), total
