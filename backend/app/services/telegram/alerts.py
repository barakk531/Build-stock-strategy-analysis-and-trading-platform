"""Signal alert formatting, queueing, and delivery with retry.

One alert per signal, enforced by a unique constraint. Only signals from the
most recent trading day are queued (never the 200k+ historical backfill).
Delivery failures record the error and retry on the next processing run until
max attempts.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.signal import Signal
from app.models.stock import Stock
from app.models.strategy import Strategy as StrategyModel
from app.models.telegram_alert import FAILED, PENDING, SENT, TelegramAlert
from app.services.telegram import client
from app.services.telegram.client import escape_html as esc

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3


def _fmt_price(value) -> str:
    return f"${float(value):,.2f}" if value is not None else "—"


def _fmt_volume(value) -> str:
    if value is None:
        return "—"
    number = float(value)
    for unit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(number) >= unit:
            return f"{number / unit:.1f}{suffix}"
    return f"{number:.0f}"


def _fmt_market_cap(value) -> str:
    if value is None:
        return "—"
    number = float(value)
    for unit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(number) >= unit:
            return f"${number / unit:.1f}{suffix}"
    return f"${number:,.0f}"


def format_signal_message(signal: Signal, stock: Stock, strategy: StrategyModel) -> str:
    """Build the alert text (HTML parse mode) per the spec's example layout."""
    settings = get_settings()
    is_buy = signal.signal_type == "BUY"
    head = "🟢 BUY SIGNAL" if is_buy else "🔴 SELL SIGNAL"

    lines = [
        f"<b>{head} — {esc(stock.symbol)}</b>",
        "",
        f"Company: {esc(stock.company_name or '—')}",
        f"Strategy: {esc(strategy.name)} v{strategy.version}",
        f"Signal date: {signal.trade_date.isoformat()}",
        f"Reference close: {_fmt_price(signal.reference_price)}",
        "Planned paper execution: Next market open",
        "",
        "Conditions:",
    ]

    payload = signal.conditions_json or {}
    for condition in payload.get("conditions", []):
        mark = "✅" if condition.get("passed") else "❌"
        lines.append(f"{mark} {esc(condition.get('label', ''))}")

    values = payload.get("values", {})
    ratio = values.get("volume_ratio")
    volume = values.get("volume")
    average = values.get("average_volume")
    if volume is not None and average is not None:
        lines.append(f"Volume: {_fmt_volume(volume)} vs average {_fmt_volume(average)}")
    if ratio is not None:
        lines.append(f"Volume ratio: {float(ratio):.2f}x")

    lines += [
        "",
        f"Market cap: {_fmt_market_cap(stock.market_cap)}",
        f"Chart: {esc(settings.frontend_base_url)}/stocks/{esc(stock.symbol)}",
    ]
    return "\n".join(lines)


def queue_new_alerts(db: Session) -> int:
    """Create PENDING alert rows for current-day signals that lack one.

    "Current" = signals whose trade_date equals the latest signal trade_date,
    respecting the alert-type setting. Historical backfill is never queued.
    Idempotent: the unique constraint skips already-queued signals.
    """
    settings = get_settings()
    if not settings.telegram_alerts_enabled:
        return 0

    latest = db.scalar(select(func.max(Signal.trade_date)))
    if latest is None:
        return 0

    query = select(Signal.id).where(Signal.trade_date == latest)
    if settings.telegram_alert_types == "buy":
        query = query.where(Signal.signal_type == "BUY")
    elif settings.telegram_alert_types == "sell":
        query = query.where(Signal.signal_type == "SELL")
    if settings.telegram_min_market_cap is not None:
        query = query.join(Stock, Stock.id == Signal.stock_id).where(
            Stock.market_cap >= settings.telegram_min_market_cap
        )

    signal_ids = list(db.scalars(query))
    if not signal_ids:
        return 0

    stmt = (
        pg_insert(TelegramAlert)
        .values([{"signal_id": sid, "status": PENDING} for sid in signal_ids])
        .on_conflict_do_nothing(constraint="uq_telegram_alerts_signal")
        .returning(TelegramAlert.id)
    )
    queued = len(db.execute(stmt).scalars().all())
    db.commit()
    logger.info("telegram queued=%d signal_date=%s", queued, latest)
    return queued


def process_pending(db: Session, *, limit: int = 50) -> dict:
    """Send queued alerts. Each failure records the error and counts an
    attempt; alerts move to FAILED after _MAX_ATTEMPTS. Safe to rerun."""
    settings = get_settings()
    if not settings.telegram_alerts_enabled:
        return {"sent": 0, "failed": 0, "skipped": "alerts disabled"}

    pending = list(
        db.scalars(
            select(TelegramAlert)
            .where(TelegramAlert.status == PENDING)
            .order_by(TelegramAlert.id)
            .limit(limit)
        )
    )
    sent = 0
    failed = 0
    for alert in pending:
        signal = db.get(Signal, alert.signal_id)
        stock = db.get(Stock, signal.stock_id) if signal else None
        strategy = db.get(StrategyModel, signal.strategy_id) if signal else None
        alert.attempt_count += 1
        alert.last_attempt_at = datetime.now(UTC)
        try:
            if signal is None or stock is None or strategy is None:
                raise client.TelegramError("signal/stock/strategy row missing")
            message_id = client.send_message(format_signal_message(signal, stock, strategy))
            alert.status = SENT
            alert.sent_at = datetime.now(UTC)
            alert.telegram_message_id = message_id
            alert.error_message = None
            sent += 1
        except client.TelegramError as exc:
            alert.error_message = str(exc)
            if alert.attempt_count >= _MAX_ATTEMPTS:
                alert.status = FAILED
                failed += 1
            logger.warning(
                "telegram send failed alert=%d attempt=%d error=%s",
                alert.id,
                alert.attempt_count,
                exc,
            )
        db.commit()

    return {"sent": sent, "failed": failed, "remaining_pending": _count_pending(db)}


def _count_pending(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(TelegramAlert).where(TelegramAlert.status == PENDING)
    ) or 0
