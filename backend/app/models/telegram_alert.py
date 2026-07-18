from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PENDING = "PENDING"
SENT = "SENT"
FAILED = "FAILED"


class TelegramAlert(Base):
    """Delivery record for one signal. The unique signal_id makes duplicate
    alerts impossible at the database level."""

    __tablename__ = "telegram_alerts"
    __table_args__ = (UniqueConstraint("signal_id", name="uq_telegram_alerts_signal"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        ForeignKey("signals.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(10), server_default=PENDING, index=True)
    attempt_count: Mapped[int] = mapped_column(server_default=text("0"))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    telegram_message_id: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
