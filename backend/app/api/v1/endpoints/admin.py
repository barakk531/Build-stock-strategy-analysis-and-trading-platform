"""Data-administration endpoints: manual syncs and data health.

No auth yet (Phase 9); do not expose these ports publicly. Sync endpoints run
synchronously in the request — fine for manual admin use; scheduled runs go
through the job layer instead.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.daily_price import DailyPrice
from app.models.stock import Stock
from app.schemas.analysis import IndicatorRecalcOut, SignalScanOut
from app.schemas.stock import (
    DataHealthOut,
    MetadataRefreshOut,
    PriceSyncOut,
    UniverseSyncOut,
)
from app.services.indicators import storage as indicator_storage
from app.services.market_data import sync as sync_service
from app.services.market_data import universe as universe_service
from app.services.signals import detector as signal_detector

router = APIRouter(prefix="/admin")

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/universe/sync", response_model=UniverseSyncOut)
def sync_universe(db: DbDep) -> UniverseSyncOut:
    try:
        return UniverseSyncOut(**universe_service.sync_universe(db))
    except universe_service.UniverseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/prices/sync", response_model=PriceSyncOut)
def sync_prices(
    db: DbDep,
    symbols: Annotated[list[str] | None, Query(description="Limit to these symbols")] = None,
    full: Annotated[bool, Query(description="Force a full-history backfill")] = False,
) -> PriceSyncOut:
    return PriceSyncOut(**sync_service.sync_prices(db, symbols=symbols, full=full))


@router.post("/metadata/refresh", response_model=MetadataRefreshOut)
def refresh_metadata(
    db: DbDep,
    symbols: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=520)] = 60,
) -> MetadataRefreshOut:
    return MetadataRefreshOut(**sync_service.refresh_metadata(db, symbols=symbols, limit=limit))


@router.post("/indicators/recalculate", response_model=IndicatorRecalcOut)
def recalculate_indicators(
    db: DbDep,
    symbols: Annotated[list[str] | None, Query()] = None,
) -> IndicatorRecalcOut:
    return IndicatorRecalcOut(**indicator_storage.recalculate(db, symbols=symbols))


@router.post("/signals/scan", response_model=SignalScanOut)
def scan_signals(
    db: DbDep,
    symbols: Annotated[list[str] | None, Query()] = None,
    strategy_id: Annotated[int | None, Query()] = None,
) -> SignalScanOut:
    try:
        result = signal_detector.scan_all(db, symbols=symbols, strategy_id=strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SignalScanOut(**result)


@router.get("/data-health", response_model=DataHealthOut)
def data_health(db: DbDep) -> DataHealthOut:
    active = db.scalar(select(func.count()).select_from(Stock).where(Stock.is_active)) or 0
    with_prices = (
        db.scalar(
            select(func.count(func.distinct(DailyPrice.stock_id)))
            .select_from(DailyPrice)
            .join(Stock, Stock.id == DailyPrice.stock_id)
            .where(Stock.is_active)
        )
        or 0
    )
    total_rows = db.scalar(select(func.count()).select_from(DailyPrice)) or 0
    latest = db.scalar(select(func.max(DailyPrice.trade_date)))

    stale_cutoff = date.today() - timedelta(days=5)
    per_stock_latest = (
        select(DailyPrice.stock_id, func.max(DailyPrice.trade_date).label("latest"))
        .group_by(DailyPrice.stock_id)
        .subquery()
    )
    stale = (
        db.scalar(
            select(func.count())
            .select_from(per_stock_latest)
            .join(Stock, Stock.id == per_stock_latest.c.stock_id)
            .where(Stock.is_active, per_stock_latest.c.latest < stale_cutoff)
        )
        or 0
    )

    return DataHealthOut(
        active_stocks=active,
        stocks_with_prices=with_prices,
        total_price_rows=total_rows,
        latest_trade_date=latest,
        stale_prices=stale,
        never_synced=max(active - with_prices, 0),
    )
