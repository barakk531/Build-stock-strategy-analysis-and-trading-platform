from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Signal(Base):
    """A BUY/SELL event for one stock/strategy/day.

    conditions_json stores the exact value of every condition at signal time so
    any historical signal stays explainable after parameters change. The unique
    constraint (incl. the parameter hash) makes duplicate detection impossible
    at the database level.
    """

    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "strategy_id",
            "trade_date",
            "signal_type",
            "parameter_hash",
            name="uq_signals_dedupe",
        ),
        Index("ix_signals_strategy_trade_date", "strategy_id", "trade_date"),
        Index("ix_signals_stock_trade_date", "stock_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    trade_date: Mapped[date] = mapped_column(Date)
    signal_type: Mapped[str] = mapped_column(String(4))  # BUY | SELL
    # Next trading day when known; None for the latest bar (no next open yet).
    execution_date: Mapped[date | None] = mapped_column(Date)
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    conditions_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    parameter_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # sha256 hex of the canonical parameter snapshot (dedupe component).
    parameter_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
