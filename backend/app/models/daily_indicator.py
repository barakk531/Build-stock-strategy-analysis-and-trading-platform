from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

_PRICE = Numeric(14, 4)


class DailyIndicator(Base, TimestampMixin):
    """Default-parameter indicators per stock/day (SMA 20/50/150 windows are
    fixed; volume average and slope here use the default 10-day settings).
    Strategy runs with custom parameters recompute their own values instead
    of reading this table."""

    __tablename__ = "daily_indicators"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_daily_indicators_stock_date"),
        Index("ix_daily_indicators_stock_trade_date", "stock_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    trade_date: Mapped[date] = mapped_column(Date)

    sma_20: Mapped[Decimal | None] = mapped_column(_PRICE)
    sma_50: Mapped[Decimal | None] = mapped_column(_PRICE)
    sma_150: Mapped[Decimal | None] = mapped_column(_PRICE)
    average_volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    volume_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    sma_150_slope: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
