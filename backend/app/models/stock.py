from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Date, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.daily_price import DailyPrice


class Stock(Base, TimestampMixin):
    """An S&P 500 company. Removed constituents are kept but marked inactive."""

    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Canonical symbol (e.g. BRK.B) and the Yahoo variant (e.g. BRK-B).
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    yahoo_symbol: Mapped[str] = mapped_column(String(20))
    company_name: Mapped[str | None] = mapped_column(String(255))
    sector: Mapped[str | None] = mapped_column(String(120), index=True)
    industry: Mapped[str | None] = mapped_column(String(160))
    exchange: Mapped[str | None] = mapped_column(String(40))
    currency: Mapped[str | None] = mapped_column(String(10))
    market_cap: Mapped[int | None] = mapped_column(BigInteger)
    is_sp500: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), index=True)
    date_added_to_index: Mapped[date | None] = mapped_column(Date)
    last_metadata_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Last successful daily-price sync for this symbol (drives incremental refresh).
    last_price_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    prices: Mapped[list[DailyPrice]] = relationship(
        back_populates="stock", cascade="all, delete-orphan", passive_deletes=True
    )
