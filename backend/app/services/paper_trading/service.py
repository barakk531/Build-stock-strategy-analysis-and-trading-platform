"""Paper-account creation, summaries, and performance assembly.

Performance reuses the backtesting metrics module on the account's snapshot
series, so backtests and paper accounts report identical statistics — the
basis for fair strategy comparison in Phase 8.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from app.core.timeutils import market_today
from app.models.daily_price import DailyPrice
from app.models.paper import AccountEquitySnapshot, PaperAccount, PaperOrder, PaperPosition
from app.models.strategy import Strategy as StrategyModel
from app.schemas.paper import AccountCreateIn
from app.services.backtesting import metrics as metrics_mod
from app.services.market_data import benchmark as benchmark_service
from app.services.signals.detector import ensure_default_strategy
from app.services.strategies.base import parameter_hash
from app.services.strategies.registry import get_strategy


def create_account(db: Session, payload: AccountCreateIn) -> PaperAccount:
    if payload.start_date > market_today():
        raise ValueError("start_date cannot be in the future")
    if payload.strategy_id is None:
        strategy_row = ensure_default_strategy(db)
    else:
        strategy_row = db.get(StrategyModel, payload.strategy_id)
        if strategy_row is None:
            raise ValueError(f"Unknown strategy id {payload.strategy_id}")

    engine = get_strategy(strategy_row.strategy_type)
    params = engine.validate_parameters(payload.parameters or strategy_row.parameters_json)
    params = params.model_copy(update={"signal_mode": "transition"})

    account = PaperAccount(
        name=payload.name,
        initial_cash=payload.initial_cash,
        cash_balance=payload.initial_cash,
        strategy_id=strategy_row.id,
        strategy_parameter_snapshot_json=engine.parameter_snapshot(params),
        parameter_hash=parameter_hash(params),
        settings_json=payload.settings.model_dump(mode="json"),
        start_date=payload.start_date,
        status="ACTIVE",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def latest_snapshot(db: Session, account_id: int) -> AccountEquitySnapshot | None:
    return db.scalar(
        select(AccountEquitySnapshot)
        .where(AccountEquitySnapshot.paper_account_id == account_id)
        .order_by(AccountEquitySnapshot.snapshot_date.desc())
        .limit(1)
    )


def summarize(db: Session, account: PaperAccount) -> dict:
    """Headline numbers for one account (detail header, single-account
    endpoints). For a list of accounts use summarize_many — three queries
    total instead of three per account."""
    return summarize_many(db, [account])[account.id]


def summarize_many(db: Session, accounts: list[PaperAccount]) -> dict[int, dict]:
    """Same headline numbers as summarize, batched: one grouped-count query
    for open positions, one for pending orders, and one latest-snapshot
    lookup per account via a LATERAL join — independent of how many accounts
    are passed, instead of 3 queries × N accounts."""
    if not accounts:
        return {}
    ids = [a.id for a in accounts]

    open_counts = dict(
        db.execute(
            select(PaperPosition.paper_account_id, func.count())
            .where(PaperPosition.paper_account_id.in_(ids), PaperPosition.status == "OPEN")
            .group_by(PaperPosition.paper_account_id)
        ).all()
    )
    pending_counts = dict(
        db.execute(
            select(PaperOrder.paper_account_id, func.count())
            .where(PaperOrder.paper_account_id.in_(ids), PaperOrder.status == "PENDING")
            .group_by(PaperOrder.paper_account_id)
        ).all()
    )
    snapshot_lateral = (
        select(AccountEquitySnapshot.total_equity, AccountEquitySnapshot.cumulative_return,
               AccountEquitySnapshot.snapshot_date)
        .where(AccountEquitySnapshot.paper_account_id == PaperAccount.id)
        .order_by(AccountEquitySnapshot.snapshot_date.desc())
        .limit(1)
        .lateral()
    )
    latest_snapshots = {
        row.id: row
        for row in db.execute(
            select(PaperAccount.id, snapshot_lateral.c.total_equity,
                   snapshot_lateral.c.cumulative_return, snapshot_lateral.c.snapshot_date)
            .select_from(PaperAccount.__table__.join(snapshot_lateral, true()))
            .where(PaperAccount.id.in_(ids))
        ).all()
    }

    out: dict[int, dict] = {}
    for account in accounts:
        snapshot = latest_snapshots.get(account.id)
        out[account.id] = {
            "total_equity": float(snapshot.total_equity)
            if snapshot
            else float(account.cash_balance),
            "total_return_pct": float(snapshot.cumulative_return) * 100 if snapshot else None,
            "open_positions": open_counts.get(account.id, 0),
            "pending_orders": pending_counts.get(account.id, 0),
            "last_snapshot_date": snapshot.snapshot_date if snapshot else None,
        }
    return out


def open_positions_with_marks(db: Session, account: PaperAccount) -> list[dict]:
    positions = list(
        db.scalars(
            select(PaperPosition)
            .where(
                PaperPosition.paper_account_id == account.id,
                PaperPosition.status == "OPEN",
            )
            .order_by(PaperPosition.symbol)
        )
    )
    if not positions:
        return []
    stock_ids = [p.stock_id for p in positions]
    latest_close = dict(
        db.execute(
            select(DailyPrice.stock_id, DailyPrice.close)
            .distinct(DailyPrice.stock_id)
            .where(DailyPrice.stock_id.in_(stock_ids))
            .order_by(DailyPrice.stock_id, DailyPrice.trade_date.desc())
        ).all()
    )
    out = []
    for position in positions:
        mark = latest_close.get(position.stock_id)
        mark = float(mark) if mark is not None else None
        quantity = float(position.quantity)
        value = quantity * mark if mark is not None else None
        entry = {
            "id": position.id,
            "symbol": position.symbol,
            "quantity": quantity,
            "average_entry_price": float(position.average_entry_price),
            "cost_basis": float(position.cost_basis),
            "opened_at": position.opened_at,
            "closed_at": None,
            "status": position.status,
            "realized_pnl": None,
            "last_price": mark,
            "market_value": round(value, 2) if value is not None else None,
            "unrealized_pnl": round(value - float(position.cost_basis), 2)
            if value is not None
            else None,
        }
        out.append(entry)
    return out


def performance(db: Session, account: PaperAccount) -> dict:
    """Full spec §13 account statistics from snapshots + closed positions."""
    snapshots = list(
        db.scalars(
            select(AccountEquitySnapshot)
            .where(AccountEquitySnapshot.paper_account_id == account.id)
            .order_by(AccountEquitySnapshot.snapshot_date)
        )
    )
    if not snapshots:
        return {
            "metrics": None,
            "equity_curve": [],
            "benchmark_curve": [],
            "monthly_returns": [],
            "yearly_returns": [],
            "open_positions": [],
            "notes": ["No trading days processed yet."],
        }

    dates = [s.snapshot_date for s in snapshots]
    equity = pd.Series([float(s.total_equity) for s in snapshots], index=dates)
    positions_value = pd.Series([float(s.positions_value) for s in snapshots], index=dates)
    initial = float(account.initial_cash)

    closed = list(
        db.scalars(
            select(PaperPosition).where(
                PaperPosition.paper_account_id == account.id,
                PaperPosition.status == "CLOSED",
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
            "holding_days": (p.closed_at - p.opened_at).days if p.closed_at else None,
        }
        for p in closed
    ]
    open_rows = open_positions_with_marks(db, account)
    trades += [{"status": "OPEN", "pnl": None, "pnl_percent": None, "holding_days": None}] * len(
        open_rows
    )

    notional = db.execute(
        select(
            PaperOrder.side,
            func.coalesce(func.sum(PaperOrder.quantity * PaperOrder.execution_price), 0),
        )
        .where(PaperOrder.paper_account_id == account.id, PaperOrder.status == "EXECUTED")
        .group_by(PaperOrder.side)
    ).all()
    by_side = {side: float(total) for side, total in notional}

    settings = account.settings_json or {}
    benchmark, benchmark_note = benchmark_service.get_series(
        db, settings.get("benchmark_symbol"), dates[0], dates[-1]
    )
    # Align to the account's own snapshot calendar (paused stretches or
    # data gaps can otherwise leave benchmark_return_pct measuring a
    # slightly different span than the account's own equity curve).
    aligned_benchmark = metrics_mod.align_benchmark(equity.index, benchmark)
    if benchmark is not None and aligned_benchmark is None:
        benchmark_note = benchmark_note or "benchmark has no overlap with account snapshots"
    benchmark = aligned_benchmark

    metrics = metrics_mod.compute_metrics(
        equity,
        positions_value,
        initial,
        trades,
        benchmark=benchmark,
        buy_notional=by_side.get("BUY", 0.0),
        sell_notional=by_side.get("SELL", 0.0),
    )

    notes = [
        "Simulated fills: next trading day's raw open with slippage and "
        "commission. Splits adjust position quantities; cash dividends are "
        "credited on the ex-date.",
        "Universe is the current S&P 500 (survivorship bias for accounts "
        "started in the past).",
    ]
    if benchmark_note:
        notes.append(benchmark_note)

    return {
        "metrics": metrics,
        "equity_curve": metrics_mod.curve_points(equity, positions_value),
        "benchmark_curve": metrics_mod.benchmark_curve_points(benchmark, equity.index, initial)
        if benchmark is not None
        else [],
        "monthly_returns": metrics_mod.period_returns(equity, initial, "ME"),
        "yearly_returns": metrics_mod.period_returns(equity, initial, "YE"),
        "open_positions": open_rows,
        "notes": notes,
    }
