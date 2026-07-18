"""Telegram alert formatting and client guards (no network, ever)."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.telegram import alerts, client


def _signal(**overrides):
    base = dict(
        signal_type="BUY",
        trade_date=date(2026, 7, 16),
        reference_price=210.50,
        conditions_json={
            "signal_type": "BUY",
            "values": {
                "adjusted_close": 210.5,
                "volume": 68_400_000.0,
                "average_volume": 55_200_000.0,
                "volume_ratio": 1.24,
            },
            "conditions": [
                {"label": "SMA 150 flat or rising over 10 trading days", "passed": True},
                {"label": "Price above SMA 150", "passed": True},
                {"label": "SMA 20 above SMA 50", "passed": True},
                {"label": "Volume at least 1x the 10-day average", "passed": True},
            ],
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


_STOCK = SimpleNamespace(symbol="AAPL", company_name="Apple Inc.", market_cap=3_100_000_000_000)
_STRATEGY = SimpleNamespace(name="SMA Trend and Volume", version=1)


def test_buy_message_matches_spec_layout():
    text = alerts.format_signal_message(_signal(), _STOCK, _STRATEGY)
    assert text.startswith("<b>🟢 BUY SIGNAL — AAPL</b>")
    assert "Company: Apple Inc." in text
    assert "Strategy: SMA Trend and Volume v1" in text
    assert "Signal date: 2026-07-16" in text
    assert "Reference close: $210.50" in text
    assert "Planned paper execution: Next market open" in text
    assert text.count("✅") == 4
    assert "Volume: 68.4M vs average 55.2M" in text
    assert "Volume ratio: 1.24x" in text
    assert "Market cap: $3.1T" in text
    assert "/stocks/AAPL" in text


def test_sell_message_header_and_no_volume_lines():
    signal = _signal(
        signal_type="SELL",
        conditions_json={
            "signal_type": "SELL",
            "values": {},
            "conditions": [
                {"label": "Price below SMA 150", "passed": True},
                {"label": "SMA 20 below SMA 50", "passed": True},
            ],
        },
    )
    text = alerts.format_signal_message(signal, _STOCK, _STRATEGY)
    assert text.startswith("<b>🔴 SELL SIGNAL — AAPL</b>")
    assert text.count("✅") == 2
    assert "Volume ratio" not in text


def test_html_is_escaped_in_dynamic_fields():
    stock = SimpleNamespace(symbol="A&B", company_name="Cats <& Dogs> Inc.", market_cap=None)
    text = alerts.format_signal_message(_signal(), stock, _STRATEGY)
    assert "Cats &lt;&amp; Dogs&gt; Inc." in text
    assert "A&amp;B</b>" in text


def test_send_message_requires_configuration(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    get_settings.cache_clear()
    with pytest.raises(client.TelegramError, match="not configured"):
        client.send_message("hi")
    get_settings.cache_clear()


def test_escape_html():
    assert client.escape_html("<b> & co") == "&lt;b&gt; &amp; co"
