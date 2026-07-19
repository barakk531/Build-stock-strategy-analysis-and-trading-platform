from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BacktestRun(Base):
    """One backtest execution: full configuration in, full results out.

    Aggregate results (metrics, equity/drawdown curves, monthly/yearly returns,
    skip summary) live in results_json; the complete trade list and the
    detailed skipped-signal list live in their own tables so they can be
    paginated. Identical data + configuration must reproduce identical results.
    """

    __tablename__ = "backtest_runs"
    __table_args__ = (Index("ix_backtest_runs_strategy_created", "strategy_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    # Strategy parameters actually used (validated snapshot) + their hash.
    parameters_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    parameter_hash: Mapped[str] = mapped_column(String(64))
    # Universe filters (symbols/sectors/market-cap bounds) + resolved size.
    universe_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Account-level settings: sizing, max positions, execution timing, benchmark.
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    commission_model_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    slippage_model_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    # PENDING | RUNNING | COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(10), server_default="PENDING", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    results_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trades: Mapped[list[BacktestTrade]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class BacktestTrade(Base):
    """A round trip (or still-open position) produced by a backtest.

    Prices are effective fill prices — next trading day's split-adjusted open
    with slippage applied. pnl fields are set only once the trade is CLOSED.
    """

    __tablename__ = "backtest_trades"
    __table_args__ = (Index("ix_backtest_trades_run_entry", "backtest_run_id", "entry_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    entry_signal_date: Mapped[date] = mapped_column(Date)
    entry_date: Mapped[date] = mapped_column(Date)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    exit_signal_date: Mapped[date | None] = mapped_column(Date)
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    commission_paid: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    pnl_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    holding_days: Mapped[int | None] = mapped_column(Integer)
    # OPEN | CLOSED
    status: Mapped[str] = mapped_column(String(6))

    run: Mapped[BacktestRun] = relationship(back_populates="trades")


class BacktestSkip(Base):
    """A signal that did not become a trade, and why.

    Reasons: max_positions, insufficient_cash, already_holding,
    same_day_conflict, no_next_open, no_price_at_execution. Sell signals for
    stocks the account never held are only counted in the run's skip summary
    (they would dominate the table with no insight).
    """

    __tablename__ = "backtest_skipped_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    backtest_run_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="CASCADE"), index=True
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    signal_date: Mapped[date] = mapped_column(Date)
    signal_type: Mapped[str] = mapped_column(String(4))
    reason: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str | None] = mapped_column(String(200))
