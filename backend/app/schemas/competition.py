from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompetitionCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    account_ids: list[int] = Field(default_factory=list)


class CompetitionUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)


class CompetitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    account_ids: list[int] = []
    account_count: int = 0


class CompetitionListOut(BaseModel):
    items: list[CompetitionOut]
    total: int


class CloneAccountIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    competition_id: int | None = None
