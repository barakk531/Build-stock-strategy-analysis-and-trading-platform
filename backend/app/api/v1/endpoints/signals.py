"""Signal listing endpoints (across stocks)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import signal_repository
from app.schemas.analysis import SignalListOut

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/signals", response_model=SignalListOut)
def list_signals(
    db: DbDep,
    strategy_id: int | None = None,
    signal_type: Annotated[str | None, Query(pattern="^(?i)(buy|sell)$")] = None,
    since: date | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SignalListOut:
    items = signal_repository.list_signals(
        db,
        strategy_id=strategy_id,
        signal_type=signal_type,
        since=since,
        limit=limit,
        offset=offset,
    )
    return SignalListOut(items=items, count=len(items))


@router.get("/signals/latest", response_model=SignalListOut)
def latest_signals(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SignalListOut:
    items = signal_repository.list_signals(db, limit=limit)
    return SignalListOut(items=items, count=len(items))
