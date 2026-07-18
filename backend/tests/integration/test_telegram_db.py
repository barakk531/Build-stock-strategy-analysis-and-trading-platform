"""Alert queue/process against real Postgres with the Telegram client mocked.

Proves: at most one alert per signal (rerun queues zero), failures retry and
then land in FAILED with the error recorded, successes store the message id,
and disabled alerts are a no-op.
"""

import os
import uuid
from datetime import date

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; start Postgres and set it to run integration tests",
)


@pytest.fixture()
def db():
    from app.db.session import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def alerts_enabled(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("TELEGRAM_ALERTS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def signal_row(db):
    """A signal on a brand-new far-future trade date so it is 'the latest'."""
    from app.models.signal import Signal
    from app.models.stock import Stock
    from app.repositories import stock_repository
    from app.services.signals import detector

    symbol = f"ZT{uuid.uuid4().hex[:6].upper()}"
    stock_repository.upsert_constituents(
        db,
        [{"symbol": symbol, "yahoo_symbol": symbol, "company_name": "Alert Test"}],
        deactivate_missing=False,
    )
    stock = stock_repository.get_by_symbol(db, symbol)
    strategy = detector.ensure_default_strategy(db)

    signal = Signal(
        stock_id=stock.id,
        strategy_id=strategy.id,
        trade_date=date(2099, 1, 3),
        signal_type="BUY",
        reference_price=100,
        conditions_json={"values": {}, "conditions": [{"label": "x", "passed": True}]},
        parameter_snapshot_json={},
        parameter_hash="t" * 64,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)

    yield signal

    db.query(Stock).filter(Stock.symbol == symbol).delete(synchronize_session=False)
    db.commit()


def test_queue_is_idempotent(db, signal_row, alerts_enabled):
    from app.services.telegram import alerts

    first = alerts.queue_new_alerts(db)
    second = alerts.queue_new_alerts(db)
    assert first >= 1
    assert second == 0  # unique constraint: one alert per signal, ever


def test_process_success_and_failure_paths(db, signal_row, alerts_enabled, monkeypatch):
    from app.models.telegram_alert import TelegramAlert
    from app.services.telegram import alerts, client

    alerts.queue_new_alerts(db)

    # Failure path: transport error -> attempts increment, stays PENDING.
    def boom(text, **kwargs):
        raise client.TelegramError("simulated outage")

    monkeypatch.setattr(client, "send_message", boom)
    result = alerts.process_pending(db)
    alert = db.scalar(
        db.query(TelegramAlert).filter(TelegramAlert.signal_id == signal_row.id).statement
    )
    assert alert.attempt_count == 1
    assert alert.status == "PENDING"
    assert "simulated outage" in alert.error_message

    # Success path: next run sends and records the message id.
    monkeypatch.setattr(client, "send_message", lambda text, **kw: "42")
    result = alerts.process_pending(db)
    db.refresh(alert)
    assert result["sent"] >= 1
    assert alert.status == "SENT"
    assert alert.telegram_message_id == "42"
    assert alert.error_message is None

    # Rerun: nothing pending for this signal, no double send.
    monkeypatch.setattr(client, "send_message", lambda text, **kw: "43")
    alerts.process_pending(db)
    db.refresh(alert)
    assert alert.telegram_message_id == "42"  # unchanged — sent exactly once


def test_failure_lands_in_failed_after_max_attempts(db, signal_row, alerts_enabled, monkeypatch):
    from app.models.telegram_alert import TelegramAlert
    from app.services.telegram import alerts, client

    alerts.queue_new_alerts(db)
    monkeypatch.setattr(
        client, "send_message",
        lambda text, **kw: (_ for _ in ()).throw(client.TelegramError("down")),
    )
    for _ in range(3):
        alerts.process_pending(db)
    alert = db.scalar(
        db.query(TelegramAlert).filter(TelegramAlert.signal_id == signal_row.id).statement
    )
    assert alert.status == "FAILED"
    assert alert.attempt_count == 3


def test_disabled_alerts_are_noop(db, signal_row, monkeypatch):
    from app.core.config import get_settings
    from app.services.telegram import alerts

    monkeypatch.setenv("TELEGRAM_ALERTS_ENABLED", "false")
    get_settings.cache_clear()
    assert alerts.queue_new_alerts(db) == 0
    assert alerts.process_pending(db)["sent"] == 0
    get_settings.cache_clear()
