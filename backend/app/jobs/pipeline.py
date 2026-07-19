"""Job bodies for the §18 schedule. Each owns a session and never raises —
failures are logged and the next run (or the manual admin endpoint) retries
naturally thanks to idempotent building blocks."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select

from app.core.timeutils import market_today
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def daily_market_update() -> None:
    """Prices → indicators → signals → Telegram → paper accounts."""
    from app.services.indicators import storage as indicator_storage
    from app.services.market_data import sync as sync_service
    from app.services.paper_trading import processor as paper_processor
    from app.services.signals import detector
    from app.services.telegram import alerts as telegram_alerts

    db = SessionLocal()
    try:
        prices = sync_service.sync_prices(db)
        logger.info(
            "job daily: prices synced=%s failed=%d", prices["synced"], len(prices["failed"])
        )
        indicators = indicator_storage.recalculate(db)
        logger.info("job daily: indicators %s", indicators)
        scan = detector.scan_all(db)
        logger.info("job daily: signals %s", scan)
        queued = telegram_alerts.queue_new_alerts(db)
        sent = telegram_alerts.process_pending(db)
        logger.info("job daily: telegram queued=%d result=%s", queued, sent)
        paper = paper_processor.process_all(db)
        logger.info("job daily: paper %s", paper)
    except Exception:
        logger.exception("daily market update failed")
    finally:
        db.close()


def weekly_universe_sync() -> None:
    from app.services.market_data import universe as universe_service

    db = SessionLocal()
    try:
        result = universe_service.sync_universe(db)
        logger.info("job universe: %s", result)
    except Exception:
        logger.exception("weekly universe sync failed")
    finally:
        db.close()


def metadata_refresh() -> None:
    from app.services.market_data import sync as sync_service

    db = SessionLocal()
    try:
        result = sync_service.refresh_metadata(db, limit=120)
        logger.info("job metadata: updated=%d failed=%d", result["updated"], len(result["failed"]))
    except Exception:
        logger.exception("metadata refresh failed")
    finally:
        db.close()


def health_check() -> None:
    """Log-level health report (spec §18): stale data and stuck work."""
    from app.models.daily_price import DailyPrice
    from app.models.paper import PaperOrder
    from app.models.stock import Stock
    from app.models.telegram_alert import TelegramAlert

    db = SessionLocal()
    try:
        latest = db.scalar(select(func.max(DailyPrice.trade_date)))
        active = db.scalar(select(func.count()).where(Stock.is_active.is_(True))) or 0
        failed_alerts = db.scalar(
            select(func.count()).where(TelegramAlert.status == "FAILED")
        ) or 0
        stuck_orders = db.scalar(
            select(func.count()).where(
                PaperOrder.status == "PENDING",
                PaperOrder.signal_date < market_today() - timedelta(days=7),
            )
        ) or 0
        stale = latest is not None and latest < market_today() - timedelta(days=5)
        level = logging.WARNING if (stale or failed_alerts or stuck_orders) else logging.INFO
        logger.log(
            level,
            "health: latest_trade_date=%s active_stocks=%d failed_alerts=%d stuck_paper_orders=%d",
            latest,
            active,
            failed_alerts,
            stuck_orders,
        )
    except Exception:
        logger.exception("health check failed")
    finally:
        db.close()
