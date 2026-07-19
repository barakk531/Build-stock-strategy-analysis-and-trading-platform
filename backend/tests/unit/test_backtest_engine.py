"""Execution-model integrity on hand-crafted data (spec §15 'Backtest integrity').

Every scenario builds a tiny price panel + explicit orders, so each rule is
verifiable by hand: next-open fills, slippage/commission arithmetic, sells
before buys, deterministic ranking, no negative cash, no naked sells, no
pyramiding, missing trading days, and rerun determinism.
"""

from datetime import date

import pandas as pd
import pytest

from app.services.backtesting.config import BacktestConfig
from app.services.backtesting.engine import (
    BacktestDataError,
    OrderIntent,
    run_simulation,
)


def _days(n, start="2026-01-05"):
    return [d.date() for d in pd.bdate_range(start, periods=n)]


def _frame(dates, opens, closes):
    return pd.DataFrame({"adj_open": opens, "adj_close": closes}, index=dates)


def _config(**overrides):
    base = dict(
        name="test",
        start_date=date(2026, 1, 5),
        end_date=date(2026, 12, 31),
        initial_cash=10_000.0,
        max_open_positions=10,
        position_size_percent=50.0,
        commission_per_trade=5.0,
        slippage_percent=1.0,
        benchmark_symbol=None,
    )
    base.update(overrides)
    return BacktestConfig(**base)


def test_next_open_fill_with_slippage_and_commission():
    days = _days(3)
    panel = {"AAA": _frame(days, [100.0, 110.0, 120.0], [100.0, 111.0, 121.0])}
    orders = [
        OrderIntent("AAA", "BUY", signal_date=days[0], execution_date=days[1]),
        OrderIntent("AAA", "SELL", signal_date=days[1], execution_date=days[2]),
    ]
    result = run_simulation(_config(), panel, orders)

    trade = result.trades[0]
    # Buy fills at day-2 OPEN (never the signal close): 110 * 1.01 slippage.
    assert trade.entry_price == pytest.approx(111.1)
    assert trade.entry_date == days[1]
    # Sizing: 50% of previous-close equity (10k) = 5000 budget - 5 commission.
    assert trade.quantity == 45  # floor(5000 / 111.1), whole shares
    # Sell fills at day-3 open with slippage against us: 120 * 0.99.
    assert trade.exit_price == pytest.approx(118.8)
    expected_pnl = (45 * 118.8 - 5) - (45 * 111.1 + 5)
    assert trade.pnl == pytest.approx(expected_pnl)
    assert trade.status == "CLOSED"
    assert trade.holding_days == (days[2] - days[1]).days

    # Equity checks: day 2 = cash + 45 shares at close 111.
    cash_after_buy = 10_000 - (45 * 111.1 + 5)
    assert result.equity.loc[days[1], "cash"] == pytest.approx(cash_after_buy)
    assert result.equity.loc[days[1], "equity"] == pytest.approx(cash_after_buy + 45 * 111.0)
    assert result.executed_buys == 1
    assert result.executed_sells == 1


def test_cash_never_negative_and_budget_respects_cash():
    days = _days(4)
    panel = {
        "AAA": _frame(days, [100.0] * 4, [100.0] * 4),
        "BBB": _frame(days, [100.0] * 4, [100.0] * 4),
        "CCC": _frame(days, [100.0] * 4, [100.0] * 4),
    }
    # 60% sizing x3 buys: the third must shrink to remaining cash, never negative.
    orders = [
        OrderIntent(sym, "BUY", signal_date=days[0], execution_date=days[1], volume_ratio=vr)
        for sym, vr in (("AAA", 3.0), ("BBB", 2.0), ("CCC", 1.0))
    ]
    config = _config(position_size_percent=60.0, commission_per_trade=0.0, slippage_percent=0.0)
    result = run_simulation(config, panel, orders)

    assert (result.equity["cash"] >= 0).all()
    quantities = {t.symbol: t.quantity for t in result.trades}
    assert quantities["AAA"] == 60  # 6000 / 100
    assert quantities["BBB"] == 40  # only 4000 cash left
    assert "CCC" not in quantities  # nothing left
    skip = [s for s in result.skips if s.symbol == "CCC"][0]
    assert skip.reason == "insufficient_cash"


def test_ranking_and_max_positions():
    days = _days(3)
    panel = {s: _frame(days, [100.0] * 3, [100.0] * 3) for s in ("AAA", "BBB", "CCC")}
    orders = [
        OrderIntent("AAA", "BUY", days[0], days[1], volume_ratio=1.1),
        OrderIntent("BBB", "BUY", days[0], days[1], volume_ratio=3.0),
        OrderIntent("CCC", "BUY", days[0], days[1], volume_ratio=2.0),
    ]
    config = _config(max_open_positions=2, position_size_percent=10.0)
    result = run_simulation(config, panel, orders)

    filled = {t.symbol for t in result.trades}
    assert filled == {"BBB", "CCC"}  # highest volume ratios win
    assert result.skip_summary == {"max_positions": 1}
    assert result.skips[0].symbol == "AAA"


def test_no_sell_without_position_and_no_pyramiding():
    days = _days(4)
    panel = {"AAA": _frame(days, [100.0] * 4, [100.0] * 4)}
    orders = [
        OrderIntent("AAA", "SELL", days[0], days[1]),  # nothing held -> summary only
        OrderIntent("AAA", "BUY", days[0], days[1]),
        OrderIntent("AAA", "BUY", days[1], days[2]),  # already holding
    ]
    result = run_simulation(_config(), panel, orders)

    assert result.skip_summary["sell_no_position"] == 1
    assert result.skip_summary["already_holding"] == 1
    # Naked sell is counted but not row-detailed (would dominate the table).
    assert all(s.reason != "sell_no_position" for s in result.skips)
    assert len([t for t in result.trades if t.symbol == "AAA"]) == 1


def test_sells_execute_before_buys_and_free_cash():
    days = _days(4)
    panel = {
        "AAA": _frame(days, [100.0] * 4, [100.0] * 4),
        "BBB": _frame(days, [100.0] * 4, [100.0] * 4),
    }
    config = _config(position_size_percent=100.0, commission_per_trade=0.0, slippage_percent=0.0)
    orders = [
        OrderIntent("AAA", "BUY", days[0], days[1]),
        OrderIntent("AAA", "SELL", days[1], days[2]),
        OrderIntent("BBB", "BUY", days[1], days[2]),  # funded by the AAA sale
    ]
    result = run_simulation(config, panel, orders)

    assert result.executed_sells == 1
    assert result.executed_buys == 2
    bbb = [t for t in result.trades if t.symbol == "BBB"][0]
    assert bbb.entry_date == days[2]
    assert bbb.quantity == 100  # full equity redeployed same day


def test_same_day_conflict_never_rebuys_sold_stock():
    days = _days(3)
    panel = {"AAA": _frame(days, [100.0] * 3, [100.0] * 3)}
    orders = [
        OrderIntent("AAA", "BUY", days[0], days[1]),
        OrderIntent("AAA", "SELL", days[1], days[2]),
        OrderIntent("AAA", "BUY", days[1], days[2]),  # same execution day as the sell
    ]
    result = run_simulation(_config(), panel, orders)
    assert result.skip_summary.get("same_day_conflict") == 1
    assert len([t for t in result.trades if t.status == "OPEN"]) == 0


def test_no_next_open_stays_unexecuted():
    days = _days(2)
    panel = {"AAA": _frame(days, [100.0, 101.0], [100.0, 101.0])}
    orders = [OrderIntent("AAA", "BUY", signal_date=days[1], execution_date=None)]
    result = run_simulation(_config(), panel, orders)
    assert result.trades == []
    assert result.skip_summary == {"no_next_open": 1}


def test_missing_trading_day_fills_on_next_available_and_marks_ffill():
    days = _days(4)
    gapped = [days[0], days[1], days[3]]  # stock does not trade on days[2]
    panel = {
        "AAA": _frame(days, [100.0] * 4, [100.0] * 4),
        "GAP": _frame(gapped, [50.0, 52.0, 60.0], [51.0, 53.0, 61.0]),
    }
    config = _config(position_size_percent=10.0, commission_per_trade=0.0, slippage_percent=0.0)
    # Signal on GAP's day 2; its next trading day is days[3], not days[2].
    orders = [OrderIntent("GAP", "BUY", signal_date=days[1], execution_date=days[3])]
    result = run_simulation(config, panel, orders)

    trade = result.trades[0]
    assert trade.entry_date == days[3]
    assert trade.entry_price == pytest.approx(60.0)
    # On the day GAP does not trade, the portfolio still marks (no position yet
    # here, but the calendar row exists and equity stays defined).
    assert result.equity.loc[days[2], "equity"] == pytest.approx(10_000.0)


def test_open_position_at_end_is_marked_not_sold():
    days = _days(3)
    panel = {"AAA": _frame(days, [100.0] * 3, [100.0, 100.0, 130.0])}
    config = _config(position_size_percent=10.0, commission_per_trade=0.0, slippage_percent=0.0)
    orders = [OrderIntent("AAA", "BUY", days[0], days[1])]
    result = run_simulation(config, panel, orders)

    trade = result.trades[0]
    assert trade.status == "OPEN"
    assert trade.exit_price is None  # never invented
    assert result.open_positions[0]["last_price"] == pytest.approx(130.0)
    assert result.open_positions[0]["unrealized_pnl"] == pytest.approx(10 * 30.0)
    assert result.equity.loc[days[2], "equity"] == pytest.approx(10_000 - 1000 + 10 * 130.0)


def test_fractional_shares_when_enabled():
    days = _days(2)
    panel = {"AAA": _frame(days, [333.0, 333.0], [333.0, 333.0])}
    config = _config(
        allow_fractional_shares=True,
        position_size_percent=10.0,
        commission_per_trade=0.0,
        slippage_percent=0.0,
    )
    orders = [OrderIntent("AAA", "BUY", days[0], days[1])]
    result = run_simulation(config, panel, orders)
    assert result.trades[0].quantity == pytest.approx(3.003, abs=1e-4)


def test_rerun_is_deterministic():
    days = _days(6)
    panel = {
        "AAA": _frame(days, [100, 101, 102, 103, 104, 105], [100, 101, 102, 103, 104, 105]),
        "BBB": _frame(days, [50, 51, 52, 53, 54, 55], [50, 51, 52, 53, 54, 55]),
    }
    orders = [
        OrderIntent("AAA", "BUY", days[0], days[1], volume_ratio=2.0),
        OrderIntent("BBB", "BUY", days[0], days[1], volume_ratio=1.5),
        OrderIntent("AAA", "SELL", days[3], days[4]),
    ]
    first = run_simulation(_config(), panel, orders)
    second = run_simulation(_config(), panel, orders)

    assert first.trades == second.trades
    assert first.skip_summary == second.skip_summary
    pd.testing.assert_frame_equal(first.equity, second.equity)


def test_empty_panel_raises():
    with pytest.raises(BacktestDataError):
        run_simulation(_config(), {}, [])
