"""Signal + indicator persistence against real Postgres (skips without DB).

Proves: default-strategy seeding is idempotent, signal rerun inserts zero
duplicates, different parameters create distinct signals, and indicator
storage upserts idempotently.
"""

import os
import uuid

import numpy as np
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
def stock_with_prices(db):
    """A throwaway stock with 40 days of trending prices (cleaned up after)."""
    from app.models.stock import Stock
    from app.repositories import price_repository, stock_repository
    from app.services.market_data import downloader

    symbol = f"ZQ{uuid.uuid4().hex[:6].upper()}"
    stock_repository.upsert_constituents(
        db,
        [{"symbol": symbol, "yahoo_symbol": symbol, "company_name": "Signal IT"}],
        deactivate_missing=False,
    )
    stock = stock_repository.get_by_symbol(db, symbol)

    prices = list(np.linspace(100, 130, 40))
    volumes = [1000.0] * 38 + [4000.0, 4000.0]
    frame = pd.DataFrame(
        {
            "Open": prices, "High": [p + 1 for p in prices], "Low": [p - 1 for p in prices],
            "Close": prices, "Adj Close": prices, "Volume": volumes,
            "Dividends": [0.0] * 40, "Stock Splits": [0.0] * 40,
        },
        index=pd.bdate_range("2026-05-01", periods=40),
    )
    price_repository.upsert_prices(db, stock.id, downloader.frame_to_rows(frame))

    yield stock

    db.query(Stock).filter(Stock.symbol == symbol).delete(synchronize_session=False)
    db.commit()


_SMALL_PARAMS = {
    "sma_short_window": 3, "sma_medium_window": 5, "sma_long_window": 10,
    "sma_150_slope_lookback_days": 3, "volume_average_days": 5,
}


def test_default_strategy_seed_is_idempotent(db):
    from app.models.strategy import Strategy
    from app.services.signals import detector

    first = detector.ensure_default_strategy(db)
    second = detector.ensure_default_strategy(db)
    assert first.id == second.id
    count = (
        db.query(Strategy)
        .filter(Strategy.strategy_type == "sma_trend_volume", Strategy.version == 1)
        .count()
    )
    assert count == 1


def test_scan_persists_once_and_dedupes_reruns(db, stock_with_prices):
    from app.repositories import signal_repository
    from app.services.signals import detector

    strategy_row = detector.ensure_default_strategy(db)

    first = detector.scan_stock(
        db, stock_with_prices, strategy_row, parameters=_SMALL_PARAMS
    )
    assert first["events"] >= 1
    assert first["inserted"] == first["events"]

    rerun = detector.scan_stock(
        db, stock_with_prices, strategy_row, parameters=_SMALL_PARAMS
    )
    assert rerun["events"] == first["events"]
    assert rerun["inserted"] == 0  # duplicate-proof

    stored = signal_repository.list_signals(db, stock_id=stock_with_prices.id)
    assert len(stored) == first["events"]
    assert stored[0].conditions_json["conditions"]  # explanation persisted
    assert stored[0].parameter_snapshot_json["sma_long_window"] == 10


def test_different_parameters_create_distinct_signals(db, stock_with_prices):
    from app.repositories import signal_repository
    from app.services.signals import detector

    strategy_row = detector.ensure_default_strategy(db)
    detector.scan_stock(db, stock_with_prices, strategy_row, parameters=_SMALL_PARAMS)

    other = {**_SMALL_PARAMS, "volume_multiplier": 2.0}
    result = detector.scan_stock(db, stock_with_prices, strategy_row, parameters=other)
    # Different parameter hash -> its events insert as separate rows.
    stored = signal_repository.list_signals(db, stock_id=stock_with_prices.id)
    hashes = {s.parameter_hash for s in stored}
    assert len(hashes) == (2 if result["events"] else 1)


def test_indicator_storage_idempotent(db, stock_with_prices):
    from app.repositories import indicator_repository
    from app.services.indicators import storage

    written_first = storage.recalculate_for_stock(db, stock_with_prices)
    written_second = storage.recalculate_for_stock(db, stock_with_prices)
    assert written_first == written_second == 40

    rows = indicator_repository.get_indicators(db, stock_with_prices.id)
    assert len(rows) == 40
    latest = rows[-1]
    assert latest.sma_20 is not None  # 40 rows -> SMA20 exists on the tail
    assert latest.sma_150 is None  # not enough history for 150
