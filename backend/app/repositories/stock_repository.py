"""Data access for stocks. All queries live here — services never build SQL."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.stock import Stock


def get_by_symbol(db: Session, symbol: str) -> Stock | None:
    return db.scalar(select(Stock).where(Stock.symbol == symbol.upper()))


def list_stocks(
    db: Session,
    *,
    active_only: bool = True,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Stock], int]:
    """Return (page, total) of stocks, optionally filtered."""
    query = select(Stock)
    if active_only:
        query = query.where(Stock.is_active.is_(True))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            Stock.symbol.ilike(pattern) | Stock.company_name.ilike(pattern)
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Stock.symbol).limit(limit).offset(offset)).all()
    return list(rows), total


def list_active_for_sync(db: Session) -> list[Stock]:
    return list(db.scalars(select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.symbol)))


def upsert_constituents(db: Session, rows: list[dict]) -> tuple[int, int]:
    """Idempotent universe sync: insert new constituents, refresh existing ones,
    and mark stocks missing from `rows` as inactive (never delete).

    Each row needs: symbol, yahoo_symbol; optional: company_name, sector,
    industry, date_added_to_index.

    Returns (upserted_count, deactivated_count).
    """
    if not rows:
        return 0, 0

    now = datetime.now(UTC)
    for row in rows:
        row.setdefault("is_sp500", True)
        row.setdefault("is_active", True)

    stmt = pg_insert(Stock).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Stock.symbol],
        set_={
            "yahoo_symbol": stmt.excluded.yahoo_symbol,
            "company_name": stmt.excluded.company_name,
            "sector": stmt.excluded.sector,
            "industry": stmt.excluded.industry,
            "date_added_to_index": stmt.excluded.date_added_to_index,
            "is_sp500": True,
            "is_active": True,
            "updated_at": now,
        },
    )
    db.execute(stmt)

    current_symbols = [row["symbol"] for row in rows]
    deactivated = (
        db.query(Stock)
        .filter(Stock.is_active.is_(True), Stock.symbol.notin_(current_symbols))
        .update({"is_active": False, "updated_at": now}, synchronize_session=False)
    )
    db.commit()
    # Bulk statements bypass the identity map and expire_on_commit=False keeps
    # loaded objects alive — expire them so later reads see the new state.
    db.expire_all()
    return len(rows), deactivated


def update_metadata(db: Session, stock: Stock, meta: dict) -> None:
    """Apply refreshed company metadata (market cap, exchange, ...)."""
    for field in ("company_name", "sector", "industry", "exchange", "currency", "market_cap"):
        value = meta.get(field)
        if value is not None:
            setattr(stock, field, value)
    stock.last_metadata_update = datetime.now(UTC)
    db.commit()


def mark_price_sync(db: Session, stock: Stock, when: datetime | None = None) -> None:
    stock.last_price_sync = when or datetime.now(UTC)
    db.commit()
