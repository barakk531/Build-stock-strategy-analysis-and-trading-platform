"""Performance statistics computed from an equity curve and a trade list.

Pure functions on pandas/floats — no database, no I/O — so every number the
spec requires (Sharpe, Sortino, drawdown, monthly returns, ...) is unit
testable in isolation. Conventions, documented for the UI:

- Annualization uses 252 trading days; the risk-free rate is 0.
- Sortino's downside deviation is sqrt(mean(min(r, 0)^2)) over all days.
- Trade statistics (win rate, profit factor, averages) cover CLOSED trades
  only; open positions contribute unrealized value to the equity curve.
- Exposure is the average fraction of equity held in positions.
- Turnover is annualized: ((buys + sells) / 2) / average equity / years.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return round(float(value), digits)


def _to_datetime_series(series: pd.Series) -> pd.Series:
    """Equity indexed by datetime for resampling (input index is date objects)."""
    out = series.copy()
    out.index = pd.to_datetime(out.index)
    return out


def align_benchmark(equity_index: pd.Index, benchmark: pd.Series | None) -> pd.Series | None:
    """Clip/forward-fill a benchmark series onto the equity calendar so
    returns are measured over the exact same span as the strategy — a raw
    benchmark series can have different start/end dates (missing data at the
    edges, a different trading calendar), which would otherwise understate or
    overstate benchmark_return_pct relative to the strategy's own window.
    Returns None when fewer than 2 points remain after alignment."""
    if benchmark is None or benchmark.empty:
        return None
    aligned = benchmark.reindex(equity_index).ffill().dropna()
    return aligned if len(aligned) >= 2 else None


def beat_market_stats(equity: pd.Series, benchmark: pd.Series | None) -> dict[str, float | None]:
    """"Beat the market" KPIs comparing an equity curve to a benchmark over
    their shared calendar: share of days the strategy's cumulative return leads
    the index, the information ratio (annualized mean/std of daily excess
    return), and up/down capture (strategy vs index on index-up and index-down
    days). All None when there is no overlap."""
    empty = {
        "pct_days_outperforming": None,
        "information_ratio": None,
        "up_capture_pct": None,
        "down_capture_pct": None,
    }
    aligned = align_benchmark(equity.index, benchmark)
    if aligned is None or equity.empty:
        return empty

    acc_curve = equity / float(equity.iloc[0])
    ben_curve = aligned / float(aligned.iloc[0])
    common = acc_curve.index.intersection(ben_curve.index)
    outperform = (
        float((acc_curve.loc[common] > ben_curve.loc[common]).mean() * 100.0)
        if len(common)
        else None
    )

    acc_ret = equity.pct_change().dropna()
    ben_ret = aligned.pct_change().dropna()
    days = acc_ret.index.intersection(ben_ret.index)
    acc_ret, ben_ret = acc_ret.loc[days], ben_ret.loc[days]
    excess = acc_ret - ben_ret
    info_ratio = (
        float(excess.mean() / excess.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))
        if len(excess) > 1 and excess.std(ddof=1) > 0
        else None
    )

    up, down = ben_ret > 0, ben_ret < 0
    up_capture = (
        float(acc_ret[up].mean() / ben_ret[up].mean() * 100.0)
        if up.any() and ben_ret[up].mean() != 0
        else None
    )
    down_capture = (
        float(acc_ret[down].mean() / ben_ret[down].mean() * 100.0)
        if down.any() and ben_ret[down].mean() != 0
        else None
    )
    return {
        "pct_days_outperforming": _round(outperform, 2),
        "information_ratio": _round(info_ratio),
        "up_capture_pct": _round(up_capture, 2),
        "down_capture_pct": _round(down_capture, 2),
    }


def drawdown_curve(equity: pd.Series) -> pd.Series:
    """Fractional drawdown from the running peak (0 at highs, negative below)."""
    return equity / equity.cummax() - 1.0


def period_returns(equity: pd.Series, initial_value: float, freq: str) -> list[dict[str, Any]]:
    """Per-period returns from period-end equity values.

    The first period is measured against `initial_value` so the first month or
    year reflects gains from actual starting capital, not from its own end.
    """
    if equity.empty:
        return []
    ts = _to_datetime_series(equity)
    period_last = ts.resample(freq).last().dropna()
    previous = period_last.shift(1)
    if len(period_last) > 0:
        previous.iloc[0] = initial_value
    returns = period_last / previous - 1.0

    out = []
    for stamp, value in returns.items():
        entry: dict[str, Any] = {"year": int(stamp.year)}
        if freq == "ME":
            entry["month"] = int(stamp.month)
        entry["return_pct"] = _round(value * 100.0)
        out.append(entry)
    return out


def trade_statistics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Win/loss statistics over CLOSED trades (each dict needs pnl, pnl_percent,
    holding_days)."""
    closed = [t for t in trades if t.get("status") == "CLOSED" and t.get("pnl") is not None]
    pnls = [float(t["pnl"]) for t in closed]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]
    gross_profit = sum(winners)
    gross_loss = -sum(losers)  # positive number

    holding = [t["holding_days"] for t in closed if t.get("holding_days") is not None]

    return {
        "trades": len(closed),
        "open_trades": sum(1 for t in trades if t.get("status") == "OPEN"),
        "win_rate_pct": _round(len(winners) / len(closed) * 100.0) if closed else None,
        "profit_factor": _round(gross_profit / gross_loss) if gross_loss > 0 else None,
        "average_winner": _round(np.mean(winners), 2) if winners else None,
        "average_loser": _round(np.mean(losers), 2) if losers else None,
        "largest_winner": _round(max(pnls), 2) if pnls else None,
        "largest_loser": _round(min(pnls), 2) if pnls else None,
        "average_holding_days": _round(np.mean(holding), 1) if holding else None,
    }


def compute_metrics(
    equity: pd.Series,
    positions_value: pd.Series,
    initial_cash: float,
    trades: list[dict[str, Any]],
    *,
    benchmark: pd.Series | None = None,
    buy_notional: float = 0.0,
    sell_notional: float = 0.0,
) -> dict[str, Any]:
    """All spec §15 outputs from the daily equity curve + trade list.

    `equity` and `positions_value` are indexed by trade date (ascending).
    `benchmark` is an adjusted-close series covering the same span (or None).
    """
    if equity.empty:
        raise ValueError("equity curve is empty")

    final_equity = float(equity.iloc[-1])
    total_return = final_equity / initial_cash - 1.0
    n_days = len(equity)
    years = n_days / TRADING_DAYS_PER_YEAR

    returns = equity.pct_change().dropna()
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    mean = float(returns.mean()) if len(returns) else 0.0

    annualized_return = (
        (final_equity / initial_cash) ** (1.0 / years) - 1.0 if years > 0 and n_days > 1 else None
    )
    volatility = std * math.sqrt(TRADING_DAYS_PER_YEAR) if std > 0 else None
    sharpe = mean / std * math.sqrt(TRADING_DAYS_PER_YEAR) if std > 0 else None

    downside = returns.clip(upper=0.0)
    downside_dev = float(np.sqrt((downside**2).mean())) if len(returns) else 0.0
    sortino = (
        mean * TRADING_DAYS_PER_YEAR / (downside_dev * math.sqrt(TRADING_DAYS_PER_YEAR))
        if downside_dev > 0
        else None
    )

    dd = drawdown_curve(equity)
    max_drawdown = float(dd.min()) if len(dd) else 0.0

    exposure = float((positions_value / equity).mean()) if len(equity) else 0.0
    mean_equity = float(equity.mean())
    turnover = (
        ((buy_notional + sell_notional) / 2.0) / mean_equity / years
        if years > 0 and mean_equity > 0
        else None
    )

    benchmark_return = None
    if benchmark is not None and len(benchmark) >= 2:
        benchmark_return = float(benchmark.iloc[-1] / benchmark.iloc[0] - 1.0)

    metrics = {
        "initial_capital": _round(initial_cash, 2),
        "final_equity": _round(final_equity, 2),
        "total_return_pct": _round(total_return * 100.0),
        "annualized_return_pct": _round(annualized_return * 100.0)
        if annualized_return is not None
        else None,
        "benchmark_return_pct": _round(benchmark_return * 100.0)
        if benchmark_return is not None
        else None,
        "excess_return_pct": _round((total_return - benchmark_return) * 100.0)
        if benchmark_return is not None
        else None,
        "max_drawdown_pct": _round(max_drawdown * 100.0),
        "sharpe_ratio": _round(sharpe),
        "sortino_ratio": _round(sortino),
        "volatility_pct": _round(volatility * 100.0) if volatility is not None else None,
        "exposure_pct": _round(exposure * 100.0),
        "annual_turnover": _round(turnover),
        "trading_days": n_days,
    }
    metrics.update(trade_statistics(trades))
    return metrics


def curve_points(equity: pd.Series, positions_value: pd.Series) -> list[list]:
    """Compact [date, equity, drawdown_pct, invested_pct] rows for the UI."""
    dd = drawdown_curve(equity)
    invested = (positions_value / equity) * 100.0
    return [
        [
            index.isoformat(),
            _round(float(equity.loc[index]), 2),
            _round(float(dd.loc[index]) * 100.0),
            _round(float(invested.loc[index]), 2),
        ]
        for index in equity.index
    ]


def benchmark_curve_points(
    benchmark: pd.Series, equity_index: pd.Index, initial_cash: float
) -> list[list]:
    """Benchmark rebased to starting capital, aligned to the equity calendar."""
    aligned = align_benchmark(equity_index, benchmark)
    if aligned is None:
        return []
    base = float(aligned.iloc[0])
    if base <= 0:
        return []
    scaled = aligned / base * initial_cash
    return [[idx.isoformat(), _round(float(val), 2)] for idx, val in scaled.items()]
