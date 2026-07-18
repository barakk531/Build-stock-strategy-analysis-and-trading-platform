"""Signal detection: run a strategy over stored prices and persist new events.

Signals are computed only from data available at each day's close; execution is
planned for the next trading day (None for the latest bar until it exists).
The signals unique constraint + parameter hash make reruns duplicate-free, and
identical data + parameters always reproduce identical signals.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.strategy import Strategy as StrategyModel
from app.repositories import price_repository, signal_repository, stock_repository
from app.services.indicators import calculator as calc
from app.services.strategies.base import Strategy, parameter_hash
from app.services.strategies.registry import get_strategy
from app.services.strategies.sma_trend_volume import SmaTrendVolumeStrategy

logger = logging.getLogger(__name__)


def ensure_default_strategy(db: Session) -> StrategyModel:
    """Get-or-create the seed strategy row (SMA Trend and Volume v1)."""
    engine_cls = SmaTrendVolumeStrategy
    existing = db.scalar(
        select(StrategyModel).where(
            StrategyModel.strategy_type == engine_cls.strategy_type,
            StrategyModel.version == engine_cls.version,
            StrategyModel.name == engine_cls.name,
        )
    )
    if existing:
        return existing
    row = StrategyModel(
        name=engine_cls.name,
        description=engine_cls.description,
        strategy_type=engine_cls.strategy_type,
        version=engine_cls.version,
        parameters_json=engine_cls().parameter_snapshot(None),
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("seeded default strategy id=%d %s v%d", row.id, row.name, row.version)
    return row


def engine_for(strategy_row: StrategyModel) -> Strategy:
    return get_strategy(strategy_row.strategy_type)


def scan_stock(
    db: Session,
    stock,
    strategy_row: StrategyModel,
    *,
    parameters: dict | None = None,
    persist: bool = True,
) -> dict:
    """Run the strategy for one stock; optionally persist new signals."""
    engine = engine_for(strategy_row)
    params = engine.validate_parameters(parameters or strategy_row.parameters_json)
    snapshot = engine.parameter_snapshot(params)
    params_hash = parameter_hash(params)

    prices = price_repository.get_prices(db, stock.id)
    if len(prices) < params.sma_long_window + 1:
        return {
            "symbol": stock.symbol,
            "events": 0,
            "inserted": 0,
            "reason": "insufficient history",
        }

    frame = calc.prices_to_frame(prices)
    events = engine.generate_signals(frame, params)

    inserted = 0
    if persist and events:
        rows = [
            {
                "stock_id": stock.id,
                "strategy_id": strategy_row.id,
                "trade_date": event.trade_date,
                "signal_type": event.signal_type,
                "execution_date": event.execution_date,
                "reference_price": event.reference_price,
                "conditions_json": event.conditions_payload(),
                "parameter_snapshot_json": snapshot,
                "parameter_hash": params_hash,
            }
            for event in events
        ]
        inserted = signal_repository.insert_signals(db, rows)

    return {"symbol": stock.symbol, "events": len(events), "inserted": inserted}


def scan_all(
    db: Session,
    *,
    symbols: list[str] | None = None,
    strategy_id: int | None = None,
) -> dict:
    """Detect and persist signals for active stocks. Idempotent."""
    if strategy_id is not None:
        strategy_row = db.get(StrategyModel, strategy_id)
        if strategy_row is None:
            raise ValueError(f"Unknown strategy id {strategy_id}")
    else:
        strategy_row = ensure_default_strategy(db)

    stocks = stock_repository.list_active_for_sync(db)
    if symbols:
        wanted = {s.upper() for s in symbols}
        stocks = [s for s in stocks if s.symbol in wanted]

    scanned = 0
    new_signals = 0
    skipped = 0
    failed: list[dict] = []
    for stock in stocks:
        try:
            result = scan_stock(db, stock, strategy_row)
        except Exception as exc:
            logger.exception("signal scan failed symbol=%s", stock.symbol)
            failed.append({"symbol": stock.symbol, "reason": str(exc)})
            continue
        if result.get("reason"):
            skipped += 1
            continue
        scanned += 1
        new_signals += result["inserted"]

    logger.info(
        "signal scan strategy=%d scanned=%d new=%d skipped=%d failed=%d",
        strategy_row.id,
        scanned,
        new_signals,
        skipped,
        len(failed),
    )
    return {
        "strategy_id": strategy_row.id,
        "scanned": scanned,
        "new_signals": new_signals,
        "skipped": skipped,
        "failed": failed,
    }
