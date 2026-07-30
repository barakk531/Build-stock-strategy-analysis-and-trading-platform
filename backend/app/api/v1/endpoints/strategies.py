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

from app.core.security import require_admin
from app.db.session import get_db
from app.models.strategy import Strategy as StrategyModel
from app.repositories import price_repository, stock_repository
from app.schemas.analysis import (
    ConditionOut,
    EvaluateOut,
    EvaluateRequest,
    EventOut,
    StrategyCreateIn,
    StrategyOut,
)
from app.services.indicators import calculator as calc
from app.services.signals import detector
from app.services.strategies import blocks, presets
from app.services.strategies.registry import STRATEGIES
from app.services.strategies.registry import get_strategy as get_engine

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]
AdminDep = Depends(require_admin)


def _strategy_or_404(db: Session, strategy_id: int) -> StrategyModel:
    row = db.get(StrategyModel, strategy_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown strategy id {strategy_id}")
    return row


@router.get("/strategy-blocks")
def strategy_blocks() -> dict:
    """Catalog of indicators, comparisons, and operand types the builder UI
    offers. Public and static — the single source of truth for the block menu."""
    return blocks.catalog()


@router.get("/strategies", response_model=list[StrategyOut])
def list_strategies(db: DbDep) -> list[StrategyOut]:
    detector.ensure_default_strategy(db)
    return list(db.scalars(select(StrategyModel).order_by(StrategyModel.id)))


@router.post("/strategies", response_model=StrategyOut, status_code=201, dependencies=[AdminDep])
def create_strategy(payload: StrategyCreateIn, db: DbDep) -> StrategyOut:
    """Create a user-composed strategy. Validates the parameters through the
    engine so a malformed rule set is rejected (422) before it is stored."""
    if payload.strategy_type not in STRATEGIES:
        raise HTTPException(
            status_code=422, detail=f"Unknown strategy_type {payload.strategy_type!r}"
        )
    engine = get_engine(payload.strategy_type)
    try:
        params = engine.validate_parameters(payload.parameters)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = db.scalar(
        select(StrategyModel).where(
            StrategyModel.name == payload.name, StrategyModel.version == engine.version
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"A strategy named {payload.name!r} exists")

    row = StrategyModel(
        name=payload.name,
        description=payload.description,
        strategy_type=payload.strategy_type,
        version=engine.version,
        parameters_json=engine.parameter_snapshot(params),
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/strategies/seed-presets", response_model=list[StrategyOut], dependencies=[AdminDep]
)
def seed_preset_strategies(db: DbDep) -> list[StrategyOut]:
    """Get-or-create the built-in preset strategies (idempotent)."""
    return presets.seed_presets(db)


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
    if len(prices) < engine.min_history(params):
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
