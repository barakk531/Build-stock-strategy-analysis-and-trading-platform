"""Market-data integration against real Postgres (skips without DATABASE_URL).

Network is never touched: universe HTML and Yahoo frames are fixtures. These
prove the spec's idempotency requirements — duplicate sync creates no
duplicate rows, and removed constituents get deactivated, not deleted.
"""

import os
import uuid

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; start Postgres and set it to run integration tests",
)


@pytest.fixture()
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def cleanup_symbols(db):
    """Track test symbols and remove them (and their prices) afterwards."""
    from app.models.stock import Stock

    created: list[str] = []
    yield created
    if created:
        db.query(Stock).filter(Stock.symbol.in_(created)).delete(synchronize_session=False)
        db.commit()


def _unique_symbol(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:6].upper()}"


def test_upsert_constituents_idempotent_and_deactivates(db, cleanup_symbols):
    from app.models.stock import Stock
    from app.repositories import stock_repository

    sym_a = _unique_symbol("ZZA")
    sym_b = _unique_symbol("ZZB")
    cleanup_symbols.extend([sym_a, sym_b])

    # A partial universe deactivates every symbol not in it — snapshot the
    # shared dev DB's active set so it can be restored no matter what.
    before_active = {s.symbol for s in db.query(Stock).filter(Stock.is_active).all()}
    try:
        rows = [
            {"symbol": sym_a, "yahoo_symbol": sym_a, "company_name": "Test A"},
            {"symbol": sym_b, "yahoo_symbol": sym_b, "company_name": "Test B"},
        ]
        stock_repository.upsert_constituents(
            db, [dict(r) for r in rows], deactivate_missing=False
        )
        stock_repository.upsert_constituents(  # rerun: no dupes
            db, [dict(r) for r in rows], deactivate_missing=False
        )

        stored = db.query(Stock).filter(Stock.symbol.in_([sym_a, sym_b])).all()
        assert len(stored) == 2
        assert all(s.is_active for s in stored)

        # Next sync drops sym_b -> deactivated, never deleted.
        stock_repository.upsert_constituents(db, [dict(rows[0])])
        a = stock_repository.get_by_symbol(db, sym_a)
        b = stock_repository.get_by_symbol(db, sym_b)
        assert a.is_active is True
        assert b is not None and b.is_active is False
    finally:
        if before_active:
            db.query(Stock).filter(Stock.symbol.in_(before_active)).update(
                {"is_active": True}, synchronize_session=False
            )
            db.commit()
            db.expire_all()


def test_price_upsert_idempotent_and_revising(db, cleanup_symbols):
    from app.repositories import price_repository, stock_repository
    from app.services.market_data import downloader

    sym = _unique_symbol("ZZP")
    cleanup_symbols.append(sym)
    stock_repository.upsert_constituents(
        db,
        [{"symbol": sym, "yahoo_symbol": sym, "company_name": "Price Test"}],
        deactivate_missing=False,
    )
    stock = stock_repository.get_by_symbol(db, sym)

    frame = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [10.5, 11.5],
            "Low": [9.5, 10.5],
            "Close": [10.2, 11.2],
            "Adj Close": [10.1, 11.1],
            "Volume": [1000, 2000],
            "Dividends": [0.0, 0.0],
            "Stock Splits": [0.0, 0.0],
        },
        index=pd.to_datetime(["2026-07-16", "2026-07-17"]),
    )
    rows = downloader.frame_to_rows(frame)

    written_first = price_repository.upsert_prices(db, stock.id, rows)
    written_second = price_repository.upsert_prices(db, stock.id, rows)  # rerun
    assert written_first == written_second == 2
    assert price_repository.count_for_stock(db, stock.id) == 2  # no duplicates

    # Revised data for an existing date overwrites in place.
    rows[1]["close"] = 99.9
    price_repository.upsert_prices(db, stock.id, [rows[1]])
    stored = price_repository.get_prices(db, stock.id)
    assert float(stored[-1].close) == pytest.approx(99.9)
    assert price_repository.count_for_stock(db, stock.id) == 2

    assert str(price_repository.latest_trade_date(db, stock.id)) == "2026-07-17"


def test_sync_prices_uses_mocked_downloader(db, cleanup_symbols, monkeypatch):
    """Full orchestrator path with the network layer mocked out."""
    from app.repositories import price_repository, stock_repository
    from app.services.market_data import sync as sync_service

    sym = _unique_symbol("ZZS")
    cleanup_symbols.append(sym)
    stock_repository.upsert_constituents(
        db,
        [{"symbol": sym, "yahoo_symbol": sym, "company_name": "Sync Test"}],
        deactivate_missing=False,
    )
    stock = stock_repository.get_by_symbol(db, sym)

    frame = pd.DataFrame(
        {
            "Open": [20.0],
            "High": [21.0],
            "Low": [19.0],
            "Close": [20.5],
            "Adj Close": [20.4],
            "Volume": [500],
            "Dividends": [0.0],
            "Stock Splits": [0.0],
        },
        index=pd.to_datetime(["2026-07-17"]),
    )
    monkeypatch.setattr(
        sync_service.downloader,
        "download_history",
        lambda symbols, **kw: {s: frame for s in symbols},
    )

    result = sync_service.sync_prices(db, symbols=[sym])
    assert result["synced"] == 1
    assert result["rows"] == 1
    assert result["failed"] == []
    assert price_repository.count_for_stock(db, stock.id) == 1
    db.refresh(stock)
    assert stock.last_price_sync is not None
