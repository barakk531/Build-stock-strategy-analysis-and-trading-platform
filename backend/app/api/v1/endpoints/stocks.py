"""Stock listing, detail, and price-series endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import price_repository, stock_repository
from app.schemas.stock import PriceSeriesOut, StockListOut, StockOut

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]

_MAX_PAGE = 500


@router.get("/stocks", response_model=StockListOut)
def list_stocks(
    db: DbDep,
    search: Annotated[str | None, Query(max_length=60)] = None,
    active_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StockListOut:
    items, total = stock_repository.list_stocks(
        db, active_only=active_only, search=search, limit=limit, offset=offset
    )
    return StockListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/stocks/{symbol}", response_model=StockOut)
def get_stock(symbol: str, db: DbDep) -> StockOut:
    stock = stock_repository.get_by_symbol(db, symbol)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol.upper()}")
    return stock


@router.get("/stocks/{symbol}/prices", response_model=PriceSeriesOut)
def get_stock_prices(
    symbol: str,
    db: DbDep,
    start: date | None = None,
    end: date | None = None,
    limit: Annotated[int | None, Query(ge=1, le=10000)] = None,
) -> PriceSeriesOut:
    stock = stock_repository.get_by_symbol(db, symbol)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol.upper()}")
    prices = price_repository.get_prices(db, stock.id, start=start, end=end, limit=limit)
    return PriceSeriesOut(symbol=stock.symbol, count=len(prices), prices=prices)
