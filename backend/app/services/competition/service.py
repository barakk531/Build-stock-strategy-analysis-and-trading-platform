"""Strategy competition: fairness checks, leaderboard, comparison curves.

Nothing is precomputed — every read derives from the members' current
snapshots over their COMMON window [max(first snapshot), min(last snapshot)],
so accounts of different ages still compare on overlapping days. Fair
comparison (spec §14) is surfaced as explicit checks, and the leaderboard
always carries risk (Sharpe, drawdown) alongside returns — the default
ordering is Sharpe, never total return alone.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.competition import Competition, CompetitionAccount
from app.models.paper import AccountEquitySnapshot, PaperAccount, PaperPosition
from app.models.strategy import Strategy as StrategyModel
from app.schemas.paper import AccountCreateIn
from app.services.backtesting import metrics as metrics_mod
from app.services.market_data import benchmark as benchmark_service
from app.services.paper_trading import service as paper_service

logger = logging.getLogger(__name__)

# Fairness dimensions (spec §14): key, label, and how to read the value.
_FAIRNESS_CHECKS = [
    ("start_date", "Same starting date", lambda a, s: a.start_date.isoformat()),
    ("initial_cash", "Same initial capital", lambda a, s: float(a.initial_cash)),
    (
        "universe",
        "Same stock universe",
        lambda a, s: "cap {}..{}".format(
            s.get("minimum_market_cap") or "—", s.get("maximum_market_cap") or "—"
        ),
    ),
    ("commission", "Same commission", lambda a, s: s.get("commission_per_trade")),
    ("slippage", "Same slippage", lambda a, s: s.get("slippage_percent")),
    ("benchmark", "Same benchmark", lambda a, s: s.get("benchmark_symbol")),
]


def parameter_summary(snapshot: dict) -> str:
    """Compact human summary of a strategy parameter snapshot."""
    if not snapshot:
        return "defaults"
    parts = []
    s, m, lo = (
        snapshot.get("sma_short_window"),
        snapshot.get("sma_medium_window"),
        snapshot.get("sma_long_window"),
    )
    if s and m and lo:
        parts.append(f"SMA {s}/{m}/{lo}")
    if snapshot.get("volume_multiplier") is not None:
        parts.append(f"vol×{snapshot['volume_multiplier']:g}")
    if snapshot.get("sma_150_min_slope_percent") is not None:
        parts.append(f"slope≥{snapshot['sma_150_min_slope_percent']:g}%")
    if snapshot.get("volume_average_days") is not None:
        parts.append(f"avg {snapshot['volume_average_days']}d")
    return " · ".join(parts) or "custom"


def fairness_report(accounts: list[PaperAccount]) -> dict:
    """Spec §14 fair-comparison checks; 'data availability' is checked against
    each account's latest snapshot date by the caller (needs the DB)."""
    checks = []
    all_fair = True
    for key, label, getter in _FAIRNESS_CHECKS:
        values = {a.name: getter(a, a.settings_json or {}) for a in accounts}
        fair = len({repr(v) for v in values.values()}) <= 1
        all_fair &= fair
        checks.append({"key": key, "label": label, "fair": fair, "values": values})
    return {"fair": all_fair, "checks": checks}


def _member_accounts(db: Session, competition: Competition) -> list[PaperAccount]:
    rows = db.scalars(
        select(PaperAccount)
        .join(CompetitionAccount, CompetitionAccount.paper_account_id == PaperAccount.id)
        .where(CompetitionAccount.competition_id == competition.id)
        .order_by(PaperAccount.id)
    )
    return list(rows)


def _equity_series(db: Session, account_id: int) -> tuple[pd.Series, pd.Series]:
    snapshots = db.execute(
        select(
            AccountEquitySnapshot.snapshot_date,
            AccountEquitySnapshot.total_equity,
            AccountEquitySnapshot.positions_value,
        )
        .where(AccountEquitySnapshot.paper_account_id == account_id)
        .order_by(AccountEquitySnapshot.snapshot_date)
    ).all()
    dates = [r.snapshot_date for r in snapshots]
    equity = pd.Series([float(r.total_equity) for r in snapshots], index=dates, dtype=float)
    positions = pd.Series([float(r.positions_value) for r in snapshots], index=dates, dtype=float)
    return equity, positions


def leaderboard(db: Session, competition: Competition) -> dict[str, Any]:
    accounts = _member_accounts(db, competition)
    strategies = {
        s.id: s
        for s in db.scalars(
            select(StrategyModel).where(
                StrategyModel.id.in_({a.strategy_id for a in accounts} or {0})
            )
        )
    }

    series: dict[int, tuple[pd.Series, pd.Series]] = {}
    for account in accounts:
        equity, positions = _equity_series(db, account.id)
        if not equity.empty:
            series[account.id] = (equity, positions)

    # Common comparison window across accounts that have data.
    window_start = window_end = None
    if series:
        window_start = max(s[0].index[0] for s in series.values())
        window_end = min(s[0].index[-1] for s in series.values())
        if window_start > window_end:
            window_start = window_end = None

    # One benchmark fetch for the window (fairness flags mixed benchmarks).
    benchmark_symbols = {(a.settings_json or {}).get("benchmark_symbol") for a in accounts}
    benchmark_symbol = benchmark_symbols.pop() if len(benchmark_symbols) == 1 else None
    bench = None
    if benchmark_symbol and window_start is not None:
        bench, _ = benchmark_service.get_series(db, benchmark_symbol, window_start, window_end)

    fairness = fairness_report(accounts)
    latest_dates = {
        a.name: (series[a.id][0].index[-1].isoformat() if a.id in series else None)
        for a in accounts
    }
    data_fair = len(set(latest_dates.values())) <= 1
    fairness["checks"].append(
        {
            "key": "data_availability",
            "label": "Same data availability (latest processed day)",
            "fair": data_fair,
            "values": latest_dates,
        }
    )
    fairness["fair"] = fairness["fair"] and data_fair

    rows = []
    equity_curves: dict[str, list] = {}
    drawdown_curves: dict[str, list] = {}
    monthly: dict[str, list] = {}
    holdings: dict[str, list] = {}
    best_worst: dict[str, dict] = {}

    for account in accounts:
        strategy = strategies.get(account.strategy_id)
        row: dict[str, Any] = {
            "account_id": account.id,
            "account_name": account.name,
            "account_status": account.status,
            "strategy_name": f"{strategy.name} v{strategy.version}" if strategy else "—",
            "parameter_summary": parameter_summary(account.strategy_parameter_snapshot_json),
            "start_date": account.start_date.isoformat(),
            "initial_cash": float(account.initial_cash),
            "current_cash": float(account.cash_balance),
        }

        if account.id not in series or window_start is None:
            row["metrics"] = None
            rows.append(row)
            continue

        equity_full, positions_full = series[account.id]
        equity = equity_full.loc[window_start:window_end]
        positions = positions_full.loc[window_start:window_end]
        base = float(equity.iloc[0])

        closed = list(
            db.scalars(
                select(PaperPosition).where(
                    PaperPosition.paper_account_id == account.id,
                    PaperPosition.status == "CLOSED",
                    PaperPosition.closed_at >= window_start,
                    PaperPosition.closed_at <= window_end,
                )
            )
        )
        trades = [
            {
                "status": "CLOSED",
                "pnl": float(p.realized_pnl or 0),
                "pnl_percent": (float(p.realized_pnl or 0) / float(p.cost_basis) * 100)
                if p.cost_basis
                else None,
                "holding_days": (p.closed_at - p.opened_at).days,
            }
            for p in closed
        ]
        open_rows = paper_service.open_positions_with_marks(db, account)
        trades += [{"status": "OPEN"}] * len(open_rows)

        bench_clipped = metrics_mod.align_benchmark(equity.index, bench)

        metrics = metrics_mod.compute_metrics(
            equity, positions, base, trades, benchmark=bench_clipped
        )
        latest_equity = float(equity_full.iloc[-1])
        row["metrics"] = metrics
        row["alpha_pct"] = metrics["excess_return_pct"]
        # "Beat the S&P 500": headline verdict (alpha) + per-day KPIs.
        excess = metrics["excess_return_pct"]
        row["beats_benchmark"] = excess is not None and excess >= 0
        row["vs_benchmark_pct"] = excess
        row.update(metrics_mod.beat_market_stats(equity, bench))
        row["current_exposure_pct"] = (
            round(float(positions_full.iloc[-1]) / latest_equity * 100, 2)
            if latest_equity > 0
            else 0.0
        )

        # Rebased comparison curves (100 = window start).
        equity_curves[account.name] = [
            [d.isoformat(), round(v / base * 100, 4)] for d, v in equity.items()
        ]
        dd = metrics_mod.drawdown_curve(equity)
        drawdown_curves[account.name] = [
            [d.isoformat(), round(v * 100, 4)] for d, v in dd.items()
        ]
        monthly[account.name] = metrics_mod.period_returns(equity, base, "ME")
        holdings[account.name] = [
            {
                "symbol": p["symbol"],
                "market_value": p["market_value"],
                "unrealized_pnl": p["unrealized_pnl"],
            }
            for p in open_rows
        ]
        if closed:
            best = max(closed, key=lambda p: float(p.realized_pnl or 0))
            worst = min(closed, key=lambda p: float(p.realized_pnl or 0))
            best_worst[account.name] = {
                "best": {
                    "symbol": best.symbol,
                    "pnl": float(best.realized_pnl or 0),
                    "closed_at": best.closed_at.isoformat(),
                },
                "worst": {
                    "symbol": worst.symbol,
                    "pnl": float(worst.realized_pnl or 0),
                    "closed_at": worst.closed_at.isoformat(),
                },
            }
        rows.append(row)

    # The S&P 500 as a real, ranked competitor — the whole point is to beat it.
    # Buy-and-hold the benchmark over the common window with the same starting
    # capital, scored with the same metrics as every strategy.
    benchmark_name = None
    if bench is not None and len(bench) >= 2 and float(bench.iloc[0]) > 0:
        base_b = float(bench.iloc[0])
        initial_b = float(accounts[0].initial_cash) if accounts else 100_000.0
        equity_b = bench / base_b * initial_b
        metrics_b = metrics_mod.compute_metrics(equity_b, equity_b.copy(), initial_b, [])
        benchmark_name = f"S&P 500 ({benchmark_symbol})" if benchmark_symbol else "S&P 500"
        rows.append(
            {
                "account_id": None,
                "account_name": benchmark_name,
                "account_status": "BENCHMARK",
                "strategy_name": "Buy & Hold",
                "parameter_summary": "market index",
                "start_date": window_start.isoformat(),
                "initial_cash": round(initial_b, 2),
                "current_cash": 0.0,
                "metrics": metrics_b,
                "is_benchmark": True,
                "alpha_pct": 0.0,
                "vs_benchmark_pct": 0.0,
                "beats_benchmark": True,
                "current_exposure_pct": 100.0,
            }
        )
        equity_curves[benchmark_name] = [
            [d.isoformat(), round(v / base_b * 100, 4)] for d, v in bench.items()
        ]

    # Risk-adjusted default order: Sharpe desc, then max drawdown (shallower
    # first), then total return — never total return alone (spec §14).
    def sort_key(row: dict) -> tuple:
        m = row.get("metrics")
        if not m:
            return (1, 0, 0, 0)
        return (
            0,
            -(m["sharpe_ratio"] if m["sharpe_ratio"] is not None else float("-inf")),
            -(m["max_drawdown_pct"] if m["max_drawdown_pct"] is not None else float("-inf")),
            -(m["total_return_pct"] if m["total_return_pct"] is not None else float("-inf")),
        )

    rows.sort(key=sort_key)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank if row.get("metrics") else None

    benchmark_curve = []
    if bench is not None and len(bench) >= 2:
        bench_base = float(bench.iloc[0])
        benchmark_curve = [
            [d.isoformat(), round(v / bench_base * 100, 4)] for d, v in bench.items()
        ]

    return {
        "competition": {
            "id": competition.id,
            "name": competition.name,
            "description": competition.description,
        },
        "window": {
            "start": window_start.isoformat() if window_start else None,
            "end": window_end.isoformat() if window_end else None,
        },
        "fairness": fairness,
        "benchmark_symbol": benchmark_symbol,
        "benchmark_competitor": benchmark_name,
        "leaderboard": rows,
        "equity_curves": equity_curves,
        "drawdown_curves": drawdown_curves,
        "benchmark_curve": benchmark_curve,
        "monthly_returns": monthly,
        "holdings": holdings,
        "best_worst_trades": best_worst,
        "notes": [
            "Default ranking is risk-adjusted (Sharpe, then drawdown) — never "
            "total return alone.",
            "Curves are rebased to 100 at the start of the common window "
            "shared by all members.",
        ],
    }


def clone_account(
    db: Session,
    source: PaperAccount,
    *,
    name: str | None = None,
    competition_id: int | None = None,
) -> PaperAccount:
    """Clone a (winning) account's full configuration into a new experiment:
    same strategy, parameters, settings, capital, and start date — fresh
    history. Optionally joins a competition immediately."""
    payload = AccountCreateIn(
        name=name or f"{source.name} (clone)",
        strategy_id=source.strategy_id,
        parameters=source.strategy_parameter_snapshot_json,
        initial_cash=float(source.initial_cash),
        start_date=source.start_date,
        settings=source.settings_json or {},
    )
    clone = paper_service.create_account(db, payload)
    if competition_id is not None:
        competition = db.get(Competition, competition_id)
        if competition is not None:
            db.add(
                CompetitionAccount(competition_id=competition.id, paper_account_id=clone.id)
            )
            db.commit()
    return clone
