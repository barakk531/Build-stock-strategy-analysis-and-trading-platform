"""Metric math verified against hand-computed values (no engine, no DB)."""

from datetime import date

import pandas as pd
import pytest

from app.services.backtesting import metrics


def _series(values, start="2026-01-05"):
    dates = [d.date() for d in pd.bdate_range(start, periods=len(values))]
    return pd.Series(values, index=dates, dtype=float)


def test_core_ratios_match_hand_computation():
    # equity 100 -> 110 -> 99 -> 108.9 : returns +10%, -10%, +10%
    equity = _series([100.0, 110.0, 99.0, 108.9])
    flat_positions = _series([0.0, 0.0, 0.0, 0.0])

    out = metrics.compute_metrics(equity, flat_positions, 100.0, [])

    assert out["final_equity"] == pytest.approx(108.9)
    assert out["total_return_pct"] == pytest.approx(8.9)
    # mean r = 1/30, std (ddof=1) = 0.115470, annualized with sqrt(252)
    assert out["sharpe_ratio"] == pytest.approx(4.5826, abs=1e-3)
    # downside dev = sqrt(0.01/3); sortino = mean*252 / (dd*sqrt(252))
    assert out["sortino_ratio"] == pytest.approx(9.1652, abs=1e-3)
    # peak 110 -> trough 99
    assert out["max_drawdown_pct"] == pytest.approx(-10.0)
    assert out["volatility_pct"] == pytest.approx(0.115470 * (252**0.5) * 100, abs=1e-2)
    assert out["benchmark_return_pct"] is None
    assert out["excess_return_pct"] is None


def test_benchmark_and_excess_return():
    equity = _series([100.0, 120.0])
    positions = _series([0.0, 0.0])
    benchmark = _series([50.0, 55.0])  # +10%

    out = metrics.compute_metrics(equity, positions, 100.0, [], benchmark=benchmark)

    assert out["benchmark_return_pct"] == pytest.approx(10.0)
    assert out["excess_return_pct"] == pytest.approx(20.0 - 10.0)


def test_trade_statistics():
    trades = [
        {"status": "CLOSED", "pnl": 100.0, "pnl_percent": 10.0, "holding_days": 10},
        {"status": "CLOSED", "pnl": 50.0, "pnl_percent": 5.0, "holding_days": 20},
        {"status": "CLOSED", "pnl": -75.0, "pnl_percent": -7.5, "holding_days": 30},
        {"status": "OPEN", "pnl": None, "pnl_percent": None, "holding_days": None},
    ]
    out = metrics.trade_statistics(trades)
    assert out["trades"] == 3
    assert out["open_trades"] == 1
    assert out["win_rate_pct"] == pytest.approx(66.6667, abs=1e-3)
    assert out["profit_factor"] == pytest.approx(2.0)  # 150 / 75
    assert out["average_winner"] == pytest.approx(75.0)
    assert out["average_loser"] == pytest.approx(-75.0)
    assert out["largest_winner"] == pytest.approx(100.0)
    assert out["largest_loser"] == pytest.approx(-75.0)
    assert out["average_holding_days"] == pytest.approx(20.0)


def test_monthly_returns_first_period_uses_initial_cash():
    # Jan ends at 110 (+10% vs initial 100), Feb ends at 121 (+10% vs Jan).
    dates = [d.date() for d in pd.bdate_range("2026-01-02", "2026-02-27")]
    values = [110.0 if d.month == 1 else 121.0 for d in dates]
    equity = pd.Series(values, index=dates)

    monthly = metrics.period_returns(equity, 100.0, "ME")

    assert monthly[0] == {"year": 2026, "month": 1, "return_pct": 10.0}
    assert monthly[1] == {"year": 2026, "month": 2, "return_pct": 10.0}

    yearly = metrics.period_returns(equity, 100.0, "YE")
    assert yearly == [{"year": 2026, "return_pct": 21.0}]


def test_curve_points_and_benchmark_rebase():
    equity = _series([100.0, 90.0])
    positions = _series([50.0, 45.0])
    points = metrics.curve_points(equity, positions)
    assert points[0] == [date(2026, 1, 5).isoformat(), 100.0, 0.0, 50.0]
    assert points[1][2] == pytest.approx(-10.0)  # drawdown pct

    bench = _series([2000.0, 2200.0])
    rebased = metrics.benchmark_curve_points(bench, equity.index, 100.0)
    assert rebased[0][1] == pytest.approx(100.0)
    assert rebased[1][1] == pytest.approx(110.0)


def test_align_benchmark_clips_to_equity_calendar():
    # Benchmark has extra days at both ends and a gap in the middle (ffill).
    bench_dates = [d.date() for d in pd.bdate_range("2026-01-01", periods=8)]
    benchmark = pd.Series([100, 101, 102, 103, 104, 105, 106, 107], index=bench_dates)
    equity_dates = bench_dates[2:6]  # a strict sub-window
    aligned = metrics.align_benchmark(pd.Index(equity_dates), benchmark)
    assert list(aligned.index) == equity_dates
    assert aligned.iloc[0] == 102


def test_align_benchmark_none_when_no_overlap():
    bench_dates = [d.date() for d in pd.bdate_range("2020-01-01", periods=3)]
    benchmark = pd.Series([1.0, 2.0, 3.0], index=bench_dates)
    future_dates = [d.date() for d in pd.bdate_range("2030-01-01", periods=3)]
    assert metrics.align_benchmark(pd.Index(future_dates), benchmark) is None
    assert metrics.align_benchmark(pd.Index(future_dates), None) is None
    assert metrics.align_benchmark(pd.Index(future_dates), pd.Series(dtype=float)) is None


def test_exposure_and_turnover():
    equity = _series([100.0] * 252)  # one flat trading year
    positions = _series([50.0] * 252)
    out = metrics.compute_metrics(
        equity, positions, 100.0, [], buy_notional=100.0, sell_notional=100.0
    )
    assert out["exposure_pct"] == pytest.approx(50.0)
    # (100+100)/2 / mean equity 100 / 1 year
    assert out["annual_turnover"] == pytest.approx(1.0)


def test_beat_market_stats_leveraged_account():
    # Account earns exactly 2x the benchmark's daily return each day, over an
    # up/down oscillating index -> up & down capture both 200%, positive info
    # ratio, and its compounding curve leads the index nearly every day.
    import numpy as np

    ben_ret = np.array([0.01, -0.005] * 20)
    acc_ret = 2.0 * ben_ret
    ben = _series((100.0 * np.cumprod(1.0 + ben_ret)).tolist())
    acc = _series((100.0 * np.cumprod(1.0 + acc_ret)).tolist())

    stats = metrics.beat_market_stats(acc, ben)
    assert stats["up_capture_pct"] == pytest.approx(200.0, abs=1.0)
    assert stats["down_capture_pct"] == pytest.approx(200.0, abs=1.0)
    assert stats["information_ratio"] > 0
    assert stats["pct_days_outperforming"] > 90.0


def test_beat_market_stats_without_benchmark_is_all_none():
    acc = _series([100.0, 101.0, 102.0, 103.0])
    assert metrics.beat_market_stats(acc, None) == {
        "pct_days_outperforming": None,
        "information_ratio": None,
        "up_capture_pct": None,
        "down_capture_pct": None,
    }
