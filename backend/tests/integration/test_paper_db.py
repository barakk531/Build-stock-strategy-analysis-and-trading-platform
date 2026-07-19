"""Paper-trading pipeline against real Postgres with synthetic stocks.

Covers the Phase 7 acceptance criteria — accounts operate independently and a
signal never touches another account's state — plus fill mechanics on RAW
prices, split adjustment of live positions, dividend cash credits, idempotent
reprocessing, pause semantics, market-cap rejection, and the API round trip.

Synthetic stocks use throwaway symbols and deactivate_missing=False; signal
scans are scoped to those symbols so the shared dev database stays untouched.
"""

import os
import uuid
from datetime import date, timedelta

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; start Postgres and set it to run integration tests",
)

START = date(2025, 1, 6)
END = date(2025, 6, 27)
POP_DAY = date(2025, 2, 10)  # volume spike -> BUY transition
DIV_DAY = date(2025, 4, 15)  # cash dividend while held
CRASH_FROM = date(2025, 6, 2)  # price collapse -> SELL transition
SPLIT_DAY = date(2025, 4, 1)

PARAMS = {"volume_multiplier": 1.2}


@pytest.fixture()
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


def _price_rows(*, split: bool, dividend: bool = False):
    """Raw==adjusted rising series with one volume pop and a June crash; the
    split variant doubles RAW prices before SPLIT_DAY (adjusted continuous)."""
    dates = [d.date() for d in pd.bdate_range("2024-01-02", END)]
    rows = []
    for i, d in enumerate(dates):
        adj = 100.0 + 0.08 * i
        if d >= CRASH_FROM:
            adj = 90.0
        factor = 2.0 if (split and d < SPLIT_DAY) else 1.0
        rows.append(
            {
                "trade_date": d,
                "open": round(adj * factor, 4),
                "high": round(adj * factor * 1.01, 4),
                "low": round(adj * factor * 0.99, 4),
                "close": round(adj * factor, 4),
                "adjusted_close": round(adj, 4),
                "volume": 2_000_000 if d == POP_DAY else 1_000_000,
                "dividend": 0.5 if (dividend and d == DIV_DAY) else 0.0,
                "stock_split": 2.0 if (split and d == SPLIT_DAY) else 0.0,
            }
        )
    return rows


@pytest.fixture()
def seeded(db):
    from app.models.paper import PaperAccount
    from app.models.stock import Stock
    from app.repositories import price_repository, stock_repository
    from app.services.signals import detector

    plain = f"ZP{uuid.uuid4().hex[:6].upper()}"
    split = f"ZQ{uuid.uuid4().hex[:6].upper()}"
    stock_repository.upsert_constituents(
        db,
        [
            {"symbol": plain, "yahoo_symbol": plain, "company_name": "Paper Plain"},
            {"symbol": split, "yahoo_symbol": split, "company_name": "Paper Split"},
        ],
        deactivate_missing=False,
    )
    plain_row = stock_repository.get_by_symbol(db, plain)
    split_row = stock_repository.get_by_symbol(db, split)
    price_repository.upsert_prices(db, plain_row.id, _price_rows(split=False, dividend=True))
    price_repository.upsert_prices(db, split_row.id, _price_rows(split=True))
    # Persist this parameter set's signals for JUST the synthetic symbols.
    detector.scan_all(db, symbols=[plain, split], parameters=PARAMS)

    yield {"plain": plain, "split": split}

    db.query(PaperAccount).filter(PaperAccount.name.like("ptest %")).delete(
        synchronize_session=False
    )
    db.query(Stock).filter(Stock.symbol.in_([plain, split])).delete(synchronize_session=False)
    db.commit()


def _create(db, name, *, settings_extra=None, **overrides):
    from app.schemas.paper import AccountCreateIn
    from app.services.paper_trading import service
    from app.services.paper_trading.config import AccountSettings

    settings = AccountSettings(
        benchmark_symbol=None, commission_per_trade=1.0, **(settings_extra or {})
    )
    payload = AccountCreateIn(
        name=name,
        parameters=PARAMS,
        initial_cash=100_000.0,
        settings=settings,
        **{"start_date": START, **overrides},
    )
    return service.create_account(db, payload)


def _process(db, account, through=END):
    from app.services.paper_trading import processor

    return processor.process_account(db, account, through=through)


def test_catch_up_fills_next_open_and_snapshots_every_day(db, seeded):
    from app.models.paper import AccountEquitySnapshot, PaperOrder, PaperPosition

    account = _create(db, "ptest catchup")
    result = _process(db, account)

    assert result["executed_buys"] >= 1
    assert result["executed_sells"] >= 1
    assert result["processed_days"] > 100

    orders = db.query(PaperOrder).filter_by(paper_account_id=account.id).all()
    buy = next(o for o in orders if o.side == "BUY" and o.status == "EXECUTED")
    # Signal on the pop day, fill on the NEXT trading day at raw open + slippage.
    assert buy.signal_date == POP_DAY
    assert buy.executed_at > POP_DAY
    assert 115 < float(buy.execution_price) < 135

    closed = (
        db.query(PaperPosition)
        .filter_by(paper_account_id=account.id, status="CLOSED")
        .all()
    )
    assert closed and closed[0].closed_at >= CRASH_FROM
    assert float(closed[0].realized_pnl) < 0  # the June crash is a real loss

    snapshots = (
        db.query(AccountEquitySnapshot)
        .filter_by(paper_account_id=account.id)
        .order_by(AccountEquitySnapshot.snapshot_date)
        .all()
    )
    assert result["processed_days"] == len(snapshots)
    assert float(snapshots[0].total_equity) == pytest.approx(100_000, rel=0.01)
    assert float(snapshots[-1].cash) == float(db.get(type(account), account.id).cash_balance)
    # Drawdown is never positive; cumulative return matches equity.
    assert all(float(s.drawdown) <= 0 for s in snapshots)
    last = snapshots[-1]
    assert float(last.cumulative_return) == pytest.approx(
        float(last.total_equity) / 100_000 - 1, abs=1e-4
    )


def test_accounts_are_independent(db, seeded):
    from app.models.paper import AccountEquitySnapshot, PaperOrder

    small = _create(db, "ptest indep small", settings_extra={"position_size_percent": 10})
    big = _create(db, "ptest indep big", settings_extra={"position_size_percent": 50})
    r_small = _process(db, small)
    r_big = _process(db, big)
    assert r_small["executed_buys"] >= 1 and r_big["executed_buys"] >= 1

    def final_equity(account_id):
        return float(
            db.query(AccountEquitySnapshot.total_equity)
            .filter_by(paper_account_id=account_id)
            .order_by(AccountEquitySnapshot.snapshot_date.desc())
            .limit(1)
            .scalar()
        )

    # Same signals, different sizing -> different outcomes, disjoint state.
    assert final_equity(small.id) != final_equity(big.id)
    small_orders = {o.id for o in db.query(PaperOrder).filter_by(paper_account_id=small.id)}
    big_orders = {o.id for o in db.query(PaperOrder).filter_by(paper_account_id=big.id)}
    assert small_orders and big_orders and not (small_orders & big_orders)

    # Pausing one account never affects the other's processing.
    small.status = "PAUSED"
    db.commit()
    assert _process(db, small).get("skipped") == "PAUSED"
    assert _process(db, big) == {"account_id": big.id, "processed_days": 0}  # up to date


def test_reprocessing_is_idempotent(db, seeded):
    from app.models.paper import AccountEquitySnapshot, PaperOrder

    account = _create(db, "ptest idem")
    first = _process(db, account)
    assert first["processed_days"] > 0

    def state():
        snaps = db.query(AccountEquitySnapshot).filter_by(paper_account_id=account.id).count()
        orders = db.query(PaperOrder).filter_by(paper_account_id=account.id).count()
        return snaps, orders, float(db.get(type(account), account.id).cash_balance)

    before = state()
    second = _process(db, account)
    assert second["processed_days"] == 0
    assert state() == before


def test_split_adjusts_position_without_false_pnl(db, seeded):
    from app.models.paper import PaperOrder, PaperPosition

    account = _create(db, "ptest split")
    result = _process(db, account)
    assert result["splits_applied"] >= 1

    buy = (
        db.query(PaperOrder)
        .filter_by(paper_account_id=account.id, side="BUY", status="EXECUTED")
        .filter(PaperOrder.symbol == seeded["split"])
        .one()
    )
    position = (
        db.query(PaperPosition)
        .filter_by(paper_account_id=account.id, status="CLOSED")
        .filter(PaperPosition.symbol == seeded["split"])
        .one()
    )
    # Entry pre-split at raw ~2x (about 246); after the 2:1 split the position
    # holds twice the shares at half the entry price — cost basis unchanged.
    assert 230 < float(buy.execution_price) < 260
    assert float(position.quantity) == pytest.approx(2 * float(buy.quantity))
    assert float(position.average_entry_price) == pytest.approx(
        float(buy.execution_price) / 2, rel=1e-3
    )
    # Realized loss is the genuine crash (~-27%), not a split artifact (~-63%).
    pnl_pct = float(position.realized_pnl) / float(position.cost_basis) * 100
    assert -35 < pnl_pct < -15


def test_dividend_credits_cash_on_ex_date(db, seeded):
    from app.models.paper import AccountEquitySnapshot, PaperPosition

    account = _create(db, "ptest dividend")
    result = _process(db, account)
    assert result["dividends_credited"] >= 1

    position = (
        db.query(PaperPosition)
        .filter_by(paper_account_id=account.id)
        .filter(PaperPosition.symbol == seeded["plain"])
        .one()
    )
    day_of = (
        db.query(AccountEquitySnapshot)
        .filter_by(paper_account_id=account.id, snapshot_date=DIV_DAY)
        .one()
    )
    day_before = (
        db.query(AccountEquitySnapshot)
        .filter_by(paper_account_id=account.id)
        .filter(AccountEquitySnapshot.snapshot_date < DIV_DAY)
        .order_by(AccountEquitySnapshot.snapshot_date.desc())
        .first()
    )
    credited = float(day_of.cash) - float(day_before.cash)
    assert credited == pytest.approx(float(position.quantity) * 0.5, abs=0.02)


def test_market_cap_filter_rejects_buys(db, seeded):
    from app.models.paper import PaperOrder, PaperPosition

    account = _create(
        db, "ptest capfilter", settings_extra={"minimum_market_cap": 10**15}
    )
    result = _process(db, account)
    assert result["executed_buys"] == 0
    rejected = (
        db.query(PaperOrder)
        .filter_by(paper_account_id=account.id, status="REJECTED")
        .all()
    )
    assert rejected and all(o.rejection_reason == "filtered_market_cap" for o in rejected)
    assert db.query(PaperPosition).filter_by(paper_account_id=account.id).count() == 0


def test_start_date_in_future_rejected(db, seeded):
    with pytest.raises(ValueError, match="future"):
        _create(db, "ptest future", start_date=date.today() + timedelta(days=5))


def test_api_round_trip(db, seeded, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.paper_trading import processor

    # Signals for the synthetic symbols are already scanned; skip the
    # full-universe ensure pass inside the API path.
    monkeypatch.setattr(processor, "ensure_signals", lambda db, account: None)
    client = TestClient(app)

    created = client.post(
        "/api/v1/paper-accounts?sync=true",
        json={
            "name": "ptest api",
            "parameters": PARAMS,
            "initial_cash": 50_000,
            "start_date": START.isoformat(),
            "settings": {"benchmark_symbol": None, "position_size_percent": 25},
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    account_id = body["id"]
    assert body["status"] == "ACTIVE"

    detail = client.get(f"/api/v1/paper-accounts/{account_id}").json()
    assert detail["total_equity"] is not None
    assert detail["last_snapshot_date"] is not None

    orders = client.get(f"/api/v1/paper-accounts/{account_id}/orders").json()
    assert orders["total"] >= 1
    positions = client.get(f"/api/v1/paper-accounts/{account_id}/positions").json()
    assert positions["total"] >= 0  # may all be closed by END

    performance = client.get(f"/api/v1/paper-accounts/{account_id}/performance").json()
    assert performance["metrics"]["final_equity"] > 0
    assert performance["equity_curve"]
    assert performance["monthly_returns"]

    assert client.post(f"/api/v1/paper-accounts/{account_id}/pause").json()["status"] == "PAUSED"
    assert client.post(f"/api/v1/paper-accounts/{account_id}/resume").json()["status"] == "ACTIVE"

    renamed = client.put(
        f"/api/v1/paper-accounts/{account_id}", json={"name": "ptest api renamed"}
    )
    assert renamed.json()["name"] == "ptest api renamed"
    frozen = client.put(
        f"/api/v1/paper-accounts/{account_id}",
        json={"settings": {"position_size_percent": 5, "benchmark_symbol": None}},
    )
    assert frozen.status_code == 409  # settings frozen once orders exist

    assert client.delete(f"/api/v1/paper-accounts/{account_id}").status_code == 204
    assert client.get(f"/api/v1/paper-accounts/{account_id}").status_code == 404
