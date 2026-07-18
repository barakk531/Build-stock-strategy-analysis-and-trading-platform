from __future__ import annotations

from sqlalchemy import Boolean, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Strategy(Base, TimestampMixin):
    """A strategy configuration. Editing logic that changes historical output
    creates a new version rather than silently changing old results."""

    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_strategies_name_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    # Stable engine identifier, e.g. "sma_trend_volume" (see strategies registry).
    strategy_type: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(server_default=text("1"))
    parameters_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), index=True)
