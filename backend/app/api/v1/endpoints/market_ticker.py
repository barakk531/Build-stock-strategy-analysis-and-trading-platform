"""Market-ticker feed for the scrolling ticker bar.

Lightweight, read-only: a small deduped mixture of stocks with the latest
stored daily close, $ change, and % change. Delayed daily data, not real-time.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market_ticker import MarketTickerItem
from app.services.market_ticker import service as market_ticker

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/market-ticker", response_model=list[MarketTickerItem])
def market_ticker_feed(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=60)] = 30,
) -> list[MarketTickerItem]:
    return market_ticker.get_ticker(db, limit=limit)
