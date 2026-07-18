from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Numeric, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.stock import Stock

# Prices are split/dividend-adjusted where noted; store enough precision for
# low-priced tickers and large volumes.
_PRICE = Numeric(14, 4)
_CORP = Numeric(14, 6)


class DailyPrice(Base, TimestampMixin):
    """One trading day of OHLCV for a stock. Adjusted close drives indicators."""

    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_daily_prices_stock_date"),
        Index("ix_daily_prices_stock_trade_date", "stock_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), index=True
    )
    trade_date: Mapped[date] = mapped_column(Date)

    open: Mapped[Decimal | None] = mapped_column(_PRICE)
    high: Mapped[Decimal | None] = mapped_column(_PRICE)
    low: Mapped[Decimal | None] = mapped_column(_PRICE)
    close: Mapped[Decimal | None] = mapped_column(_PRICE)
    adjusted_close: Mapped[Decimal | None] = mapped_column(_PRICE)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    dividend: Mapped[Decimal] = mapped_column(_CORP, server_default=text("0"))
    stock_split: Mapped[Decimal] = mapped_column(_CORP, server_default=text("0"))

    stock: Mapped[Stock] = relationship(back_populates="prices")
