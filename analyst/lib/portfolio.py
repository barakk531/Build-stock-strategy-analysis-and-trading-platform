"""User holdings persisted to data/portfolio.json (gitignored, local only)."""

from __future__ import annotations

import json
import re

from lib.config import DATA_DIR
from lib.market_data import get_quote, get_stock_fundamentals

PORTFOLIO_PATH = DATA_DIR / "portfolio.json"
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")


def load_portfolio() -> list[dict]:
    """[{"ticker","shares","cost_basis"}]. Missing/corrupt file -> []."""
    try:
        raw = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
        holdings = []
        for row in raw if isinstance(raw, list) else []:
            ticker = str(row.get("ticker", "")).upper().strip()
            if not _TICKER_RE.match(ticker):
                continue
            shares = float(row.get("shares", 0) or 0)
            cost = float(row.get("cost_basis", 0) or 0)
            if shares > 0:
                holdings.append({"ticker": ticker, "shares": shares, "cost_basis": cost})
        return holdings
    except Exception:
        return []


def save_portfolio(holdings: list[dict]) -> bool:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        clean = [
            {"ticker": str(h["ticker"]).upper(), "shares": float(h["shares"]),
             "cost_basis": float(h.get("cost_basis", 0) or 0)}
            for h in holdings
            if _TICKER_RE.match(str(h.get("ticker", "")).upper()) and float(h.get("shares", 0) or 0) > 0
        ]
        PORTFOLIO_PATH.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def upsert_holding(ticker: str, shares: float, cost_basis: float) -> bool:
    ticker = (ticker or "").upper().strip()
    if not _TICKER_RE.match(ticker) or shares <= 0:
        return False
    holdings = load_portfolio()
    holdings = [h for h in holdings if h["ticker"] != ticker]
    holdings.append({"ticker": ticker, "shares": shares, "cost_basis": cost_basis})
    return save_portfolio(sorted(holdings, key=lambda h: h["ticker"]))


def remove_holding(ticker: str) -> bool:
    holdings = [h for h in load_portfolio() if h["ticker"] != (ticker or "").upper()]
    return save_portfolio(holdings)


def compute_positions(holdings: list[dict]) -> dict:
    """Enrich holdings with live values.

    Returns {"positions": [...], "total_value", "total_cost", "total_gain",
    "total_gain_pct"}; each position carries value/gain/weight/sector.
    """
    positions = []
    total_value = 0.0
    total_cost = 0.0
    for holding in holdings:
        quote = get_quote(holding["ticker"])
        price = quote.get("price")
        value = price * holding["shares"] if price else None
        cost = holding["cost_basis"] * holding["shares"]
        info = get_stock_fundamentals(holding["ticker"])
        positions.append({
            **holding,
            "price": price,
            "value": value,
            "cost": cost,
            "gain": (value - cost) if (value is not None and cost) else None,
            "gain_pct": ((value / cost - 1.0) * 100.0) if (value is not None and cost) else None,
            "change_pct": quote.get("change_pct"),
            "sector": info.get("sector") or "Other",
            "name": info.get("shortName") or holding["ticker"],
        })
        if value:
            total_value += value
        if cost:
            total_cost += cost
    for position in positions:
        position["weight"] = (position["value"] / total_value * 100.0) if (position.get("value") and total_value) else None
    gain = total_value - total_cost if total_cost else None
    return {
        "positions": positions,
        "total_value": total_value or None,
        "total_cost": total_cost or None,
        "total_gain": gain,
        "total_gain_pct": (gain / total_cost * 100.0) if (gain is not None and total_cost) else None,
    }
