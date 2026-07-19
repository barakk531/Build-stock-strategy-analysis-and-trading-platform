"""Data-administration endpoints: manual syncs and data health.

No auth yet (Phase 9); do not expose these ports publicly. Sync endpoints run
synchronously in the request — fine for manual admin use; scheduled runs go
through the job layer instead.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutils import market_today
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
from app.services.telegram import alerts as telegram_alerts
from app.services.telegram import client as telegram_client

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


@router.post("/stocks/add")
def add_stock(
    db: DbDep,
    symbol: Annotated[str, Query(min_length=1, max_length=20)],
    is_sp500: Annotated[bool, Query(description="Treat as an index constituent")] = False,
    backfill: Annotated[bool, Query(description="Download full price history now")] = True,
) -> dict:
    """Manually track a symbol (spec §3.7) — e.g. a benchmark index like ^GSPC.

    Non-S&P rows survive universe syncs and join the daily price sync; index
    symbols (leading '^') never appear in the scanner or signal scans."""
    from app.repositories import stock_repository

    stock = stock_repository.ensure_stock(db, symbol, is_sp500=is_sp500)
    synced = None
    if backfill:
        synced = sync_service.sync_prices(db, symbols=[stock.symbol], full=False)
    return {
        "symbol": stock.symbol,
        "id": stock.id,
        "is_active": stock.is_active,
        "is_sp500": stock.is_sp500,
        "sync": synced,
    }


@router.post("/telegram/test")
def telegram_test() -> dict:
    """Send a test message to the configured chat."""
    try:
        message_id = telegram_client.send_message(
            "✅ <b>Stock Strategy Platform</b> — test message. Alerts are wired up."
        )
    except telegram_client.TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"sent": True, "telegram_message_id": message_id}


@router.post("/telegram/queue")
def telegram_queue(db: DbDep) -> dict:
    """Queue alerts for the latest trading day's signals (idempotent)."""
    return {"queued": telegram_alerts.queue_new_alerts(db)}


@router.post("/telegram/process")
def telegram_process(
    db: DbDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> dict:
    """Send pending alerts with retry tracking."""
    return telegram_alerts.process_pending(db, limit=limit)


@router.post("/paper/process")
def paper_process_all(db: DbDep) -> dict:
    """Advance every ACTIVE paper account through the latest stored trading
    day (the daily job's last step, manually triggered)."""
    from app.services.paper_trading import processor

    return processor.process_all(db)


@router.get("/jobs")
def list_jobs() -> dict:
    """Scheduled jobs and their next run times (spec §16)."""
    from app.services.scheduling.scheduler import SchedulerService

    service = SchedulerService.instance
    return {
        "scheduler_running": service is not None,
        "jobs": service.jobs() if service is not None else [],
    }


@router.get("/config")
def get_config() -> dict:
    """Sanitized runtime configuration for the settings screen. Secrets are
    masked — the raw token or key never leaves the server (spec §20)."""
    from app.core.config import get_settings
    from app.core.security import auth_required

    s = get_settings()

    def mask(value: str) -> str | None:
        if not value:
            return None
        return f"{value[:4]}…{value[-4:]}" if len(value) > 8 else "…"

    return {
        "environment": s.environment,
        "version": s.app_version,
        "market_timezone": s.market_timezone,
        "scheduler_enabled": s.scheduler_enabled,
        "auth_required": auth_required(),
        "price_history_years": s.price_history_years,
        "price_sync_overlap_days": s.price_sync_overlap_days,
        "telegram": {
            "enabled": s.telegram_alerts_enabled,
            "bot_token": mask(s.telegram_bot_token),
            "chat_id": mask(s.telegram_chat_id),
            "alert_types": s.telegram_alert_types,
            "min_market_cap": s.telegram_min_market_cap,
        },
        "frontend_base_url": s.frontend_base_url,
    }


@router.get("/health-report")
def health_report(db: DbDep) -> dict:
    """Extended operational health (spec §18): stale data, stuck work,
    delivery failures — everything the admin dashboard shows."""
    from app.models.daily_indicator import DailyIndicator
    from app.models.paper import PaperAccount, PaperOrder
    from app.models.signal import Signal
    from app.models.telegram_alert import TelegramAlert

    latest_price = db.scalar(select(func.max(DailyPrice.trade_date)))
    latest_indicator = db.scalar(select(func.max(DailyIndicator.trade_date)))
    latest_signal = db.scalar(select(func.max(Signal.trade_date)))

    telegram_counts = dict(
        db.execute(
            select(TelegramAlert.status, func.count()).group_by(TelegramAlert.status)
        ).all()
    )
    stuck_orders = db.scalar(
        select(func.count()).where(
            PaperOrder.status == "PENDING",
            PaperOrder.signal_date < market_today() - timedelta(days=7),
        )
    ) or 0
    active_accounts = db.scalar(
        select(func.count()).where(PaperAccount.status == "ACTIVE")
    ) or 0
    # The unique constraint makes duplicates impossible; report the count so
    # the spec §18 check is explicit, not assumed.
    duplicate_prices = db.scalar(
        select(func.count())
        .select_from(
            select(DailyPrice.stock_id)
            .group_by(DailyPrice.stock_id, DailyPrice.trade_date)
            .having(func.count() > 1)
            .subquery()
        )
    ) or 0

    return {
        "latest_price_date": latest_price.isoformat() if latest_price else None,
        "latest_indicator_date": latest_indicator.isoformat() if latest_indicator else None,
        "latest_signal_date": latest_signal.isoformat() if latest_signal else None,
        "indicators_behind_prices": bool(
            latest_price and latest_indicator and latest_indicator < latest_price
        ),
        "duplicate_price_rows": duplicate_prices,
        "telegram_alerts": telegram_counts,
        "paper_orders_stuck": stuck_orders,
        "active_paper_accounts": active_accounts,
    }


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

    stale_cutoff = market_today() - timedelta(days=5)
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
