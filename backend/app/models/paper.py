from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class PaperAccount(Base, TimestampMixin):
    """A simulated trading account bound to one strategy configuration.

    The parameter snapshot is frozen at creation (hash included) so account
    results stay reproducible even if the strategy row's parameters change
    later. Accounts are fully independent: every position, order, and snapshot
    is keyed by account id and processing never crosses accounts.
    """

    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    base_currency: Mapped[str] = mapped_column(String(10), server_default="USD")
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    strategy_parameter_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    parameter_hash: Mapped[str] = mapped_column(String(64), index=True)
    # Sizing, costs, filters, benchmark (spec §13 account settings).
    settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    start_date: Mapped[date] = mapped_column(Date)
    # ACTIVE | PAUSED | COMPLETED
    status: Mapped[str] = mapped_column(String(10), server_default="ACTIVE", index=True)

    positions: Mapped[list[PaperPosition]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    orders: Mapped[list[PaperOrder]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )
    snapshots: Mapped[list[AccountEquitySnapshot]] = relationship(
        back_populates="account", cascade="all, delete-orphan", passive_deletes=True
    )


class PaperPosition(Base, TimestampMixin):
    """A holding. Quantities are REAL share counts on raw prices; stock splits
    multiply quantity and divide the average entry price (cost basis fixed)."""

    __tablename__ = "paper_positions"
    __table_args__ = (
        # At most one OPEN position per account+stock (no pyramiding).
        Index(
            "uq_paper_positions_open",
            "paper_account_id",
            "stock_id",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    # Effective fill including slippage; divided on splits.
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    # quantity * entry price + buy commission at open; invariant across splits.
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    opened_at: Mapped[date] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date)
    # OPEN | CLOSED
    status: Mapped[str] = mapped_column(String(6), index=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))

    account: Mapped[PaperAccount] = relationship(back_populates="positions")


class PaperOrder(Base):
    """A simulated order created from a signal; the complete audit trail.

    Orders fill at the first trading day after signal_date with data for the
    stock, at that day's raw open with slippage and commission. Rejections
    (max_positions, insufficient_cash, already_holding, same_day_conflict,
    filtered_market_cap, no_price) keep the row with a reason — the account's
    'signals that did not become trades'."""

    __tablename__ = "paper_orders"
    __table_args__ = (
        # A signal creates at most one order per account, ever.
        Index(
            "uq_paper_orders_account_signal",
            "paper_account_id",
            "signal_id",
            unique=True,
            postgresql_where=text("signal_id IS NOT NULL"),
        ),
        Index("ix_paper_orders_account_status", "paper_account_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(20))
    signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), nullable=True
    )
    side: Mapped[str] = mapped_column(String(4))  # BUY | SELL
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))  # set at execution
    signal_date: Mapped[date] = mapped_column(Date)
    scheduled_execution_date: Mapped[date | None] = mapped_column(Date)
    executed_at: Mapped[date | None] = mapped_column(Date)  # fill trade date
    execution_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))  # incl. slippage
    commission: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    slippage: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))  # cost in $
    # PENDING | EXECUTED | REJECTED | CANCELLED
    status: Mapped[str] = mapped_column(String(9), server_default="PENDING", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account: Mapped[PaperAccount] = relationship(back_populates="orders")


class AccountEquitySnapshot(Base):
    """End-of-day account state for every trading day since start."""

    __tablename__ = "account_equity_snapshots"
    __table_args__ = (
        UniqueConstraint("paper_account_id", "snapshot_date", name="uq_equity_snapshots_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date)
    cash: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    positions_value: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    total_equity: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    # Fractions (0.0123 = +1.23%), not percentages.
    daily_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    cumulative_return: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account: Mapped[PaperAccount] = relationship(back_populates="snapshots")
