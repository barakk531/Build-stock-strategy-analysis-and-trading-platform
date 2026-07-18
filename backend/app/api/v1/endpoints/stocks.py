"""Stock listing, detail, and price-series endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories import (
    indicator_repository,
    price_repository,
    signal_repository,
    stock_repository,
)
from app.schemas.analysis import (
    AnalysisOut,
    ConditionOut,
    IndicatorSeriesOut,
    SideAnalysis,
    SignalListOut,
)
from app.schemas.stock import PriceSeriesOut, StockListOut, StockOut
from app.services.indicators import calculator as calc
from app.services.signals import detector

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]

_MAX_PAGE = 500


def _stock_or_404(db: Session, symbol: str):
    stock = stock_repository.get_by_symbol(db, symbol)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol.upper()}")
    return stock


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
    return _stock_or_404(db, symbol)


@router.get("/stocks/{symbol}/prices", response_model=PriceSeriesOut)
def get_stock_prices(
    symbol: str,
    db: DbDep,
    start: date | None = None,
    end: date | None = None,
    limit: Annotated[int | None, Query(ge=1, le=10000)] = None,
) -> PriceSeriesOut:
    stock = _stock_or_404(db, symbol)
    prices = price_repository.get_prices(db, stock.id, start=start, end=end, limit=limit)
    return PriceSeriesOut(symbol=stock.symbol, count=len(prices), prices=prices)


@router.get("/stocks/{symbol}/indicators", response_model=IndicatorSeriesOut)
def get_stock_indicators(
    symbol: str,
    db: DbDep,
    start: date | None = None,
    end: date | None = None,
    limit: Annotated[int | None, Query(ge=1, le=10000)] = None,
) -> IndicatorSeriesOut:
    stock = _stock_or_404(db, symbol)
    rows = indicator_repository.get_indicators(db, stock.id, start=start, end=end, limit=limit)
    return IndicatorSeriesOut(symbol=stock.symbol, count=len(rows), indicators=rows)


@router.get("/stocks/{symbol}/signals", response_model=SignalListOut)
def get_stock_signals(
    symbol: str,
    db: DbDep,
    signal_type: Annotated[str | None, Query(pattern="^(?i)(buy|sell)$")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> SignalListOut:
    stock = _stock_or_404(db, symbol)
    items = signal_repository.list_signals(
        db, stock_id=stock.id, signal_type=signal_type, limit=limit
    )
    return SignalListOut(items=items, count=len(items))


@router.get("/stocks/{symbol}/analysis", response_model=AnalysisOut)
def get_stock_analysis(symbol: str, db: DbDep) -> AnalysisOut:
    """Condition-by-condition explanation of the latest trading day, using the
    default strategy's saved parameters."""
    stock = _stock_or_404(db, symbol)
    strategy_row = detector.ensure_default_strategy(db)
    engine = detector.engine_for(strategy_row)
    params = engine.validate_parameters(strategy_row.parameters_json)

    prices = price_repository.get_prices(db, stock.id)
    if len(prices) < 2:
        raise HTTPException(status_code=409, detail="No price history for this symbol yet")

    frame = calc.prices_to_frame(prices)
    indicators = engine.calculate_indicators(frame, params)
    latest = indicators.iloc[-1]

    values, buy_conditions = engine.explain_row(latest, params, "BUY")
    _, sell_conditions = engine.explain_row(latest, params, "SELL")

    return AnalysisOut(
        symbol=stock.symbol,
        strategy_id=strategy_row.id,
        strategy_name=f"{strategy_row.name} v{strategy_row.version}",
        as_of=indicators.index[-1],
        values=values,
        buy=SideAnalysis(
            state=all(c.passed for c in buy_conditions),
            conditions=[ConditionOut(**c.__dict__) for c in buy_conditions],
        ),
        sell=SideAnalysis(
            state=all(c.passed for c in sell_conditions),
            conditions=[ConditionOut(**c.__dict__) for c in sell_conditions],
        ),
        latest_signal=signal_repository.latest_for_stock(db, stock.id, strategy_row.id),
    )
