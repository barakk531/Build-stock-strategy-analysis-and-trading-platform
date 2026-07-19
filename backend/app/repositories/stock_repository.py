"""Data access for stocks. All queries live here — services never build SQL."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.stock import Stock


def get_by_symbol(db: Session, symbol: str) -> Stock | None:
    return db.scalar(select(Stock).where(Stock.symbol == symbol.upper()))


def ensure_stock(
    db: Session,
    symbol: str,
    *,
    company_name: str | None = None,
    is_sp500: bool = False,
) -> Stock:
    """Get-or-create a manually tracked symbol (admin additions, benchmarks).

    Non-S&P rows (is_sp500=False) stay active through universe syncs and are
    picked up by the normal price sync, but are excluded from the scanner and
    signal scans when the symbol is an index (leading '^')."""
    symbol = symbol.strip().upper()
    existing = get_by_symbol(db, symbol)
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            db.commit()
        return existing
    stock = Stock(
        symbol=symbol,
        yahoo_symbol=symbol.replace(".", "-"),
        company_name=company_name or symbol,
        is_sp500=is_sp500,
        is_active=True,
    )
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


def list_stocks(
    db: Session,
    *,
    active_only: bool = True,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Stock], int]:
    """Return (page, total) of stocks, optionally filtered. Benchmark index
    rows (leading '^') are infrastructure, never listed."""
    query = select(Stock).where(Stock.symbol.notlike("^%"))
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


def upsert_constituents(
    db: Session, rows: list[dict], *, deactivate_missing: bool = True
) -> tuple[int, int]:
    """Idempotent universe sync: insert new constituents, refresh existing ones,
    and (when deactivate_missing) mark stocks absent from `rows` as inactive —
    never delete. Callers passing a PARTIAL list must pass
    deactivate_missing=False or they will deactivate the rest of the universe;
    the real sync passes the full parsed list (parser enforces >=400 rows).

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

    deactivated = 0
    if deactivate_missing:
        current_symbols = [row["symbol"] for row in rows]
        # Only S&P rows are in scope: manually added stocks and benchmark
        # indices (is_sp500=False) are not constituents and must survive syncs.
        deactivated = (
            db.query(Stock)
            .filter(
                Stock.is_active.is_(True),
                Stock.is_sp500.is_(True),
                Stock.symbol.notin_(current_symbols),
            )
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
