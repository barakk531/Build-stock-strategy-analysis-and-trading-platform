"""Backtest orchestration: universe → signals → simulation → persisted results.

Signals are recomputed from stored prices with the run's own parameters (never
read from the signals table), so any parameter set backtests correctly. The
strategy runs in transition mode regardless of the configured signal_mode —
scan mode would emit a BUY every day a state holds, which is meaningless for
an account that does not pyramid.

Runs are stateful rows: PENDING → RUNNING → COMPLETED/FAILED with timestamps
and an error message on failure. Reruns with identical data + configuration
produce identical results (enforced by tests).
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.models.backtest import BacktestRun
from app.models.strategy import Strategy as StrategyModel
from app.repositories import backtest_repository, price_repository, stock_repository
from app.services.backtesting import metrics as metrics_mod
from app.services.backtesting.config import BacktestConfig
from app.services.backtesting.engine import (
    BacktestDataError,
    OrderIntent,
    run_simulation,
)
from app.services.indicators import calculator as calc
from app.services.market_data import benchmark as benchmark_service
from app.services.signals.detector import ensure_default_strategy
from app.services.strategies.base import parameter_hash
from app.services.strategies.registry import get_strategy

logger = logging.getLogger(__name__)


def _warmup_start(params, start: date) -> date:
    """Enough calendar history before `start` for the longest indicator window."""
    trading_days = (
        getattr(params, "sma_long_window", 200)
        + max(
            getattr(params, "sma_150_slope_lookback_days", 10),
            getattr(params, "volume_average_days", 10),
        )
        + 5
    )
    return start - timedelta(days=math.ceil(trading_days * 1.6) + 20)


def resolve_strategy(db: Session, strategy_id: int | None) -> StrategyModel:
    if strategy_id is None:
        return ensure_default_strategy(db)
    row = db.get(StrategyModel, strategy_id)
    if row is None:
        raise ValueError(f"Unknown strategy id {strategy_id}")
    return row


def create_run(db: Session, config: BacktestConfig) -> BacktestRun:
    """Validate configuration against the strategy and persist a PENDING run."""
    strategy_row = resolve_strategy(db, config.strategy_id)
    engine = get_strategy(strategy_row.strategy_type)
    params = engine.validate_parameters(config.parameters or strategy_row.parameters_json)
    params = params.model_copy(update={"signal_mode": "transition"})

    run = BacktestRun(
        strategy_id=strategy_row.id,
        name=config.name,
        parameters_json=engine.parameter_snapshot(params),
        parameter_hash=parameter_hash(params),
        universe_json={
            "symbols": config.symbols,
            "sectors": config.sectors,
            "min_market_cap": config.min_market_cap,
            "max_market_cap": config.max_market_cap,
            "survivorship_bias": True,
        },
        settings_json=config.settings_snapshot(),
        commission_model_json={"type": "per_trade", "amount": config.commission_per_trade},
        slippage_model_json={"type": "percent", "value": config.slippage_percent},
        start_date=config.start_date,
        end_date=config.end_date,
        initial_cash=config.initial_cash,
        status="PENDING",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info("backtest run created id=%d name=%r", run.id, run.name)
    return run


def _config_from_run(run: BacktestRun) -> BacktestConfig:
    settings = run.settings_json or {}
    universe = run.universe_json or {}
    costs = run.commission_model_json or {}
    slippage = run.slippage_model_json or {}
    return BacktestConfig(
        name=run.name,
        strategy_id=run.strategy_id,
        parameters=run.parameters_json or {},
        start_date=run.start_date,
        end_date=run.end_date,
        initial_cash=float(run.initial_cash),
        symbols=universe.get("symbols"),
        sectors=universe.get("sectors"),
        min_market_cap=universe.get("min_market_cap"),
        max_market_cap=universe.get("max_market_cap"),
        max_open_positions=settings.get("max_open_positions", 10),
        position_size_percent=settings.get("position_size_percent", 10.0),
        allow_fractional_shares=settings.get("allow_fractional_shares", False),
        commission_per_trade=costs.get("amount", 0.0),
        slippage_percent=slippage.get("value", 0.05),
        benchmark_symbol=settings.get("benchmark_symbol"),
    )


def _resolve_universe(db: Session, config: BacktestConfig) -> list:
    """Active tracked stocks passing the configured filters, indices excluded.

    Manually added (non-S&P) stocks are included — the scanner, signal scans,
    and paper accounts all trade them, so backtests must see the same
    universe or paper and backtest results diverge unexplainably."""
    stocks = [
        s
        for s in stock_repository.list_active_for_sync(db)
        if not s.symbol.startswith("^")
    ]
    if config.symbols:
        wanted = set(config.symbols)
        stocks = [s for s in stocks if s.symbol in wanted]
    if config.sectors:
        wanted_sectors = set(config.sectors)
        stocks = [s for s in stocks if (s.sector or "") in wanted_sectors]
    if config.min_market_cap is not None:
        stocks = [
            s for s in stocks if s.market_cap is not None and s.market_cap >= config.min_market_cap
        ]
    if config.max_market_cap is not None:
        stocks = [
            s for s in stocks if s.market_cap is not None and s.market_cap <= config.max_market_cap
        ]
    return stocks


def _execute(db: Session, run: BacktestRun) -> dict:
    config = _config_from_run(run)
    strategy_row = db.get(StrategyModel, run.strategy_id)
    engine = get_strategy(strategy_row.strategy_type)
    params = engine.validate_parameters(run.parameters_json)

    stocks = _resolve_universe(db, config)
    if not stocks:
        raise BacktestDataError("universe is empty after filters")

    warmup_start = _warmup_start(params, config.start_date)
    long_window = getattr(params, "sma_long_window", 150)

    panel: dict[str, pd.DataFrame] = {}
    orders: list[OrderIntent] = []
    stock_ids: dict[str, int] = {}
    insufficient_history = 0

    for stock in stocks:
        prices = price_repository.get_prices(
            db, stock.id, start=warmup_start, end=config.end_date
        )
        if len(prices) < long_window + 2:
            insufficient_history += 1
            continue
        frame = calc.prices_to_frame(prices)
        # Split-adjusted open: raw open scaled by the close's adjustment factor,
        # so fills across splits are on the same basis as the signal prices.
        frame["adj_open"] = frame["open"] * (frame["adjusted_close"] / frame["close"])

        events = engine.generate_signals(frame, params)
        for event in events:
            if config.start_date <= event.trade_date <= config.end_date:
                orders.append(
                    OrderIntent(
                        symbol=stock.symbol,
                        side=event.signal_type,
                        signal_date=event.trade_date,
                        execution_date=event.execution_date,
                        volume_ratio=event.values.get("volume_ratio"),
                        slope=event.values.get("sma_long_slope_percent"),
                    )
                )

        window = frame[(frame.index >= config.start_date) & (frame.index <= config.end_date)]
        if not window.empty:
            panel[stock.symbol] = window[["adj_open", "adjusted_close"]].rename(
                columns={"adjusted_close": "adj_close"}
            )
            stock_ids[stock.symbol] = stock.id

    result = run_simulation(config, panel, orders)

    benchmark, benchmark_note = benchmark_service.get_series(
        db, config.benchmark_symbol, config.start_date, config.end_date
    )

    equity = result.equity["equity"]
    if benchmark is not None:
        # Align to the equity calendar so benchmark/excess returns measure the
        # exact same span as the strategy (edge days can differ otherwise).
        benchmark = benchmark.reindex(equity.index).ffill().dropna()
        if len(benchmark) < 2:
            benchmark, benchmark_note = None, f"benchmark {config.benchmark_symbol}: no overlap"
    trade_dicts = [
        {
            "status": t.status,
            "pnl": t.pnl,
            "pnl_percent": t.pnl_percent,
            "holding_days": t.holding_days,
        }
        for t in result.trades
    ]
    computed = metrics_mod.compute_metrics(
        equity,
        result.equity["positions_value"],
        config.initial_cash,
        trade_dicts,
        benchmark=benchmark,
        buy_notional=result.buy_notional,
        sell_notional=result.sell_notional,
    )

    notes = [
        "Survivorship bias: universe is the CURRENT S&P 500 projected into the "
        "past; delisted/removed companies are missing, which inflates results.",
        "Market-cap filters use today's market cap (look-ahead when applied to "
        "old dates).",
    ]
    if benchmark_note:
        notes.append(benchmark_note)

    trade_rows = [
        {
            "backtest_run_id": run.id,
            "stock_id": stock_ids[t.symbol],
            "symbol": t.symbol,
            "quantity": round(t.quantity, 4),
            "entry_signal_date": t.entry_signal_date,
            "entry_date": t.entry_date,
            "entry_price": round(t.entry_price, 4),
            "exit_signal_date": t.exit_signal_date,
            "exit_date": t.exit_date,
            "exit_price": None if t.exit_price is None else round(t.exit_price, 4),
            "commission_paid": round(t.commission_paid, 4),
            "pnl": None if t.pnl is None else round(t.pnl, 2),
            "pnl_percent": None if t.pnl_percent is None else round(t.pnl_percent, 4),
            "holding_days": t.holding_days,
            "status": t.status,
        }
        for t in result.trades
    ]
    skip_rows = [
        {
            "backtest_run_id": run.id,
            "stock_id": stock_ids.get(s.symbol),
            "symbol": s.symbol,
            "signal_date": s.signal_date,
            "signal_type": s.signal_type,
            "reason": s.reason,
            "detail": s.detail,
        }
        for s in result.skips
        if s.symbol in stock_ids
    ]
    backtest_repository.bulk_insert_trades(db, trade_rows)
    backtest_repository.bulk_insert_skips(db, skip_rows)

    return {
        "metrics": computed,
        "signals": {
            "total": len(orders),
            "executed_buys": result.executed_buys,
            "executed_sells": result.executed_sells,
            "skipped": result.skipped_signals,
        },
        "skip_summary": result.skip_summary,
        "equity_curve": metrics_mod.curve_points(equity, result.equity["positions_value"]),
        "benchmark_curve": metrics_mod.benchmark_curve_points(
            benchmark, equity.index, config.initial_cash
        )
        if benchmark is not None
        else [],
        "monthly_returns": metrics_mod.period_returns(equity, config.initial_cash, "ME"),
        "yearly_returns": metrics_mod.period_returns(equity, config.initial_cash, "YE"),
        "open_positions": result.open_positions,
        "universe": {
            "resolved_stocks": len(stocks),
            "with_data": len(panel),
            "insufficient_history": insufficient_history,
        },
        "notes": notes,
    }


def execute_run(db: Session, run_id: int) -> BacktestRun:
    """Run a PENDING backtest to completion, recording status transitions."""
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise ValueError(f"Unknown backtest run {run_id}")

    run.status = "RUNNING"
    run.started_at = datetime.now(UTC)
    run.error_message = None
    db.commit()

    try:
        run.results_json = _execute(db, run)
        run.status = "COMPLETED"
        run.completed_at = datetime.now(UTC)
        db.commit()
        logger.info(
            "backtest completed id=%d trades=%s",
            run.id,
            run.results_json["metrics"]["trades"],
        )
    except Exception as exc:
        db.rollback()
        run = db.get(BacktestRun, run_id)
        run.status = "FAILED"
        # Expected validation/data errors are user-actionable; anything else
        # stays in the server log — raw exception text can leak internals.
        if isinstance(exc, (BacktestDataError, ValueError)):
            run.error_message = str(exc)[:2000]
        else:
            run.error_message = (
                f"Internal error ({type(exc).__name__}) — see the server log."
            )
        run.completed_at = datetime.now(UTC)
        db.commit()
        logger.exception("backtest failed id=%d", run_id)
    return run


def execute_run_in_background(run_id: int) -> None:
    """Entry point for FastAPI BackgroundTasks — owns its own session."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        execute_run(db, run_id)
    finally:
        db.close()
