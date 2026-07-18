"""Strategy read + ad-hoc evaluation endpoints.

Create/clone/edit arrive with the strategy-management UI (later phase);
evaluate supports "temporarily edit parameters and rerun" without persisting.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.strategy import Strategy as StrategyModel
from app.repositories import price_repository, stock_repository
from app.schemas.analysis import ConditionOut, EvaluateOut, EvaluateRequest, EventOut, StrategyOut
from app.services.indicators import calculator as calc
from app.services.signals import detector

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]


def _strategy_or_404(db: Session, strategy_id: int) -> StrategyModel:
    row = db.get(StrategyModel, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown strategy id {strategy_id}")
    return row


@router.get("/strategies", response_model=list[StrategyOut])
def list_strategies(db: DbDep) -> list[StrategyOut]:
    detector.ensure_default_strategy(db)
    return list(db.scalars(select(StrategyModel).order_by(StrategyModel.id)))


@router.get("/strategies/{strategy_id}", response_model=StrategyOut)
def get_strategy(strategy_id: int, db: DbDep) -> StrategyOut:
    return _strategy_or_404(db, strategy_id)


@router.post("/strategies/{strategy_id}/evaluate", response_model=EvaluateOut)
def evaluate_strategy(strategy_id: int, request: EvaluateRequest, db: DbDep) -> EvaluateOut:
    """Run the strategy on one symbol with optional parameter overrides.
    Nothing is persisted — this is the what-if endpoint."""
    strategy_row = _strategy_or_404(db, strategy_id)
    stock = stock_repository.get_by_symbol(db, request.symbol)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {request.symbol.upper()}")

    engine = detector.engine_for(strategy_row)
    merged = {**strategy_row.parameters_json, **(request.parameters or {})}
    try:
        params = engine.validate_parameters(merged)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    prices = price_repository.get_prices(db, stock.id)
    if len(prices) < params.sma_long_window + 1:
        raise HTTPException(status_code=409, detail="Insufficient price history for these windows")

    frame = calc.prices_to_frame(prices)
    events = engine.generate_signals(frame, params)
    return EvaluateOut(
        symbol=stock.symbol,
        strategy_id=strategy_row.id,
        parameters=engine.parameter_snapshot(params),
        events=[
            EventOut(
                trade_date=e.trade_date,
                signal_type=e.signal_type,
                reference_price=e.reference_price,
                execution_date=e.execution_date,
                values=e.values,
                conditions=[ConditionOut(**c.__dict__) for c in e.conditions],
            )
            for e in events
        ],
    )
