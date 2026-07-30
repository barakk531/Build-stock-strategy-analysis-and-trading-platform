"""Market-ticker endpoint against real Postgres (skips without DB).

Proves the feed is small, deduped, well-typed (no NaN/inf), respects the limit
cap, and that the dollar change reconciles with the price and the percentage.
"""

import math
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; start Postgres and set it to run integration tests",
)


def test_ticker_returns_wellformed_deduped_items(client):
    resp = client.get("/api/v1/market-ticker?limit=25")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) <= 25
    if not items:
        pytest.skip("no priced stocks in the database")

    symbols = [it["symbol"] for it in items]
    assert len(symbols) == len(set(symbols))  # each stock at most once

    for it in items:
        assert set(it) >= {"symbol", "price", "change", "change_percent", "trade_date"}
        assert isinstance(it["symbol"], str) and it["symbol"]
        for key in ("price", "change", "change_percent"):
            assert isinstance(it[key], (int, float))
            assert math.isfinite(it[key])  # never NaN or inf


def test_change_reconciles_with_price_and_percent(client):
    items = client.get("/api/v1/market-ticker?limit=15").json()
    if not items:
        pytest.skip("no priced stocks in the database")
    for it in items:
        price, pct = it["price"], it["change_percent"]
        prev = price / (1 + pct / 100.0)
        # price/change/pct are each rounded to 2dp independently, so recomputing
        # change from the rounded pct drifts by ~price*5e-5 (a 0.005-point pct
        # rounding); scale the tolerance by price so high-priced names pass.
        tol = max(0.03, price * 1e-4)
        assert it["change"] == pytest.approx(price - prev, abs=tol)


def test_limit_is_validated_and_capped(client):
    # Endpoint declares le=60.
    assert client.get("/api/v1/market-ticker?limit=1000").status_code == 422
    assert len(client.get("/api/v1/market-ticker?limit=5").json()) <= 5
