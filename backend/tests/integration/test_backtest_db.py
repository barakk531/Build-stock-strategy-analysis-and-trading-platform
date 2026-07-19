"""Full backtest pipeline against real Postgres with synthetic stocks.

Proves the spec §15 integrity items that need the whole path (prices → signals
→ simulation → persistence): rerun determinism, truncation invariance (no
future data changes past entries), split-adjusted fills (no false profit),
status transitions, and the FAILED path.

Synthetic stocks use throwaway symbols and deactivate_missing=False so the
real universe in the shared dev database is never touched.
"""

import os
import uuid
from datetime import date

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; start Postgres and set it to run integration tests",
)

START = date(2025, 1, 6)
END = date(2025, 6, 27)
POP_DAY = date(2025, 2, 10)  # volume spike -> BUY transition
CRASH_FROM = date(2025, 6, 2)  # price collapse -> SELL transition
SPLIT_DAY = date(2025, 4, 1)


@pytest.fixture()
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


def _price_rows(*, split: bool):
    """Business-day series 2024-01-02..END: rising adjusted close, flat volume
    with one pop, June crash. Raw prices double before SPLIT_DAY when split=True."""
    dates = [d.date() for d in pd.bdate_range("2024-01-02", END)]
    rows = []
    for i, d in enumerate(dates):
        adj = 100.0 + 0.08 * i
        if d >= CRASH_FROM:
            adj = 90.0
        factor = 2.0 if (split and d < SPLIT_DAY) else 1.0
        volume = 2_000_000 if d == POP_DAY else 1_000_000
        rows.append(
            {
                "trade_date": d,
                "open": round(adj * factor, 4),
                "high": round(adj * factor * 1.01, 4),
                "low": round(adj * factor * 0.99, 4),
                "close": round(adj * factor, 4),
                "adjusted_close": round(adj, 4),
                "volume": volume,
                "dividend": 0.0,
                "stock_split": 2.0 if (split and d == SPLIT_DAY) else 0.0,
            }
        )
    return rows


@pytest.fixture()
def seeded(db):
    """Two synthetic stocks (one with a 2:1 split) with full price history."""
    from app.models.backtest import BacktestRun
    from app.models.stock import Stock
    from app.repositories import price_repository, stock_repository

    plain = f"ZB{uuid.uuid4().hex[:6].upper()}"
    split = f"ZC{uuid.uuid4().hex[:6].upper()}"
    stock_repository.upsert_constituents(
        db,
        [
            {"symbol": plain, "yahoo_symbol": plain, "company_name": "Backtest Plain"},
            {"symbol": split, "yahoo_symbol": split, "company_name": "Backtest Split"},
        ],
        deactivate_missing=False,
    )
    plain_row = stock_repository.get_by_symbol(db, plain)
    split_row = stock_repository.get_by_symbol(db, split)
    price_repository.upsert_prices(db, plain_row.id, _price_rows(split=False))
    price_repository.upsert_prices(db, split_row.id, _price_rows(split=True))

    yield {"plain": plain, "split": split}

    db.query(BacktestRun).filter(BacktestRun.name.like("itest %")).delete(
        synchronize_session=False
    )
    db.query(Stock).filter(Stock.symbol.in_([plain, split])).delete(synchronize_session=False)
    db.commit()


def _config(symbols, *, name, end=END, **overrides):
    from app.services.backtesting.config import BacktestConfig

    base = dict(
        name=name,
        start_date=START,
        end_date=end,
        initial_cash=100_000.0,
        symbols=symbols,
        parameters={"volume_multiplier": 1.2},
        commission_per_trade=1.0,
        slippage_percent=0.05,
        benchmark_symbol=None,  # never hit the network in tests
    )
    base.update(overrides)
    return BacktestConfig(**base)


def _run(db, config):
    from app.services.backtesting import runner

    run = runner.create_run(db, config)
    return runner.execute_run(db, run.id)


def test_full_run_completes_with_round_trip_and_persisted_results(db, seeded):
    from app.repositories import backtest_repository

    run = _run(db, _config([seeded["plain"]], name="itest full"))

    assert run.status == "COMPLETED", run.error_message
    results = run.results_json
    assert results["signals"]["executed_buys"] >= 1
    assert results["signals"]["executed_sells"] >= 1

    trades, total = backtest_repository.list_trades(db, run.id)
    assert total == results["metrics"]["trades"] + results["metrics"]["open_trades"]
    closed = [t for t in trades if t.status == "CLOSED"]
    assert closed, "expected at least one closed round trip"
    trade = closed[0]
    # Entry executes the day AFTER the volume-pop signal at that open.
    assert trade.entry_signal_date == POP_DAY
    assert trade.entry_date > POP_DAY
    # Fill ~ adjusted open with slippage, on the adjusted scale (~123 by Feb
    # 2025), and the June crash exit is a real loss on adjusted prices.
    assert 115 < float(trade.entry_price) < 135
    assert trade.exit_date >= CRASH_FROM

    curve = results["equity_curve"]
    assert curve[0][1] == pytest.approx(100_000.0)
    assert curve[-1][1] == pytest.approx(results["metrics"]["final_equity"])
    assert results["monthly_returns"] and results["yearly_returns"]
    assert any("Survivorship" in note for note in results["notes"])


def test_rerun_identical_and_truncation_invariant(db, seeded):
    from app.repositories import backtest_repository

    first = _run(db, _config([seeded["plain"]], name="itest det A"))
    second = _run(db, _config([seeded["plain"]], name="itest det B"))
    assert first.status == second.status == "COMPLETED"
    assert first.results_json == second.results_json  # bit-identical outcomes

    # Truncation: shortening the window must not change earlier ENTRIES —
    # signals never depend on future rows.
    shorter = _run(db, _config([seeded["plain"]], name="itest trunc", end=date(2025, 4, 30)))
    full_trades, _ = backtest_repository.list_trades(db, first.id)
    short_trades, _ = backtest_repository.list_trades(db, shorter.id)
    full_entries = [(t.entry_signal_date, t.entry_date, float(t.entry_price)) for t in full_trades]
    short_entries = [
        (t.entry_signal_date, t.entry_date, float(t.entry_price)) for t in short_trades
    ]
    assert short_entries == full_entries[: len(short_entries)]
    assert len(short_entries) >= 1


def test_split_does_not_create_false_profit_or_loss(db, seeded):
    from app.repositories import backtest_repository

    run = _run(db, _config([seeded["split"]], name="itest split"))
    assert run.status == "COMPLETED", run.error_message

    trades, _ = backtest_repository.list_trades(db, run.id)
    closed = [t for t in trades if t.status == "CLOSED"]
    assert closed
    trade = closed[0]
    # Entry is BEFORE the split (raw price ~2x adjusted). A raw-open fill would
    # show ~246 and a ~-63% collapse after the split; the adjusted fill (~123)
    # keeps the loss at the genuine June-crash size (~-27%).
    assert trade.entry_date < SPLIT_DAY < trade.exit_date
    assert 115 < float(trade.entry_price) < 135
    assert -35 < float(trade.pnl_percent) < -15


def test_failed_run_records_error(db, seeded):
    run = _run(db, _config(["ZZNOSUCH"], name="itest fail"))
    assert run.status == "FAILED"
    assert "universe is empty" in run.error_message
    assert run.completed_at is not None


def test_api_create_poll_and_delete(db, seeded):
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    payload = {
        "name": "itest api",
        "start_date": START.isoformat(),
        "end_date": END.isoformat(),
        "initial_cash": 50_000,
        "symbols": [seeded["plain"]],
        "parameters": {"volume_multiplier": 1.2},
        "benchmark_symbol": None,
    }
    created = client.post("/api/v1/backtests?sync=true", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "COMPLETED"
    assert body["total_return_pct"] is not None

    detail = client.get(f"/api/v1/backtests/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["results_json"]["metrics"]["final_equity"] > 0

    trades = client.get(f"/api/v1/backtests/{body['id']}/trades")
    assert trades.status_code == 200
    assert trades.json()["total"] >= 1

    listing = client.get("/api/v1/backtests")
    assert any(item["id"] == body["id"] for item in listing.json()["items"])

    deleted = client.delete(f"/api/v1/backtests/{body['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/backtests/{body['id']}").status_code == 404


def test_create_rejected_when_concurrency_limit_reached(db, seeded):
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import app
    from app.services.backtesting import runner

    # Fill the queue with PENDING runs (created, never executed) up to the cap.
    limit = get_settings().max_concurrent_backtests
    for i in range(limit):
        runner.create_run(db, _config([seeded["plain"]], name=f"itest cap {i}"))

    client = TestClient(app)
    payload = {
        "name": "itest cap over",
        "start_date": START.isoformat(),
        "end_date": END.isoformat(),
        "initial_cash": 50_000,
        "symbols": [seeded["plain"]],
        "parameters": {"volume_multiplier": 1.2},
        "benchmark_symbol": None,
    }
    resp = client.post("/api/v1/backtests", json=payload)
    assert resp.status_code == 429, resp.text
    assert "limit" in resp.json()["detail"].lower()
