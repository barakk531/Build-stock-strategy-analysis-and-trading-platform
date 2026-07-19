from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Competition(Base, TimestampMixin):
    """A named group of paper accounts compared over their common window.

    The comparison window and fairness checks are derived from the member
    accounts at read time — a competition stores no results of its own, so the
    leaderboard is always current.
    """

    __tablename__ = "competitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    members: Mapped[list[CompetitionAccount]] = relationship(
        back_populates="competition", cascade="all, delete-orphan", passive_deletes=True
    )


class CompetitionAccount(Base):
    """Membership link. Deleting an account removes it from competitions."""

    __tablename__ = "competition_accounts"
    __table_args__ = (
        UniqueConstraint("competition_id", "paper_account_id", name="uq_competition_account"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    competition_id: Mapped[int] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), index=True
    )
    paper_account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_accounts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    competition: Mapped[Competition] = relationship(back_populates="members")
