"""Descriptive technical & fundamental scores (0-100 each).

These are factual composites for the Snapshot gauges — labeled "Technical
strength" and "Fundamental quality" in the UI. They are NOT buy/sell signals
and are never phrased as advice; drivers are plain observations ("Price above
200DMA", "ROE 31%").
"""

from __future__ import annotations

import pandas as pd


def rsi(closes: pd.Series, period: int = 14) -> float | None:
    """Classic Wilder RSI on a close series; None if not enough data."""
    closes = closes.dropna().astype(float)
    if len(closes) <= period:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    last_loss = float(loss.iloc[-1])
    if last_loss == 0:
        return 100.0
    rs = float(gain.iloc[-1]) / last_loss
    return 100.0 - 100.0 / (1.0 + rs)


def technical_facts(daily: pd.DataFrame) -> dict:
    """Raw technical observations from ~1y of daily bars (None-safe)."""
    out = {
        "price": None, "sma50": None, "sma200": None, "above_200dma": None,
        "above_50dma": None, "rsi": None, "ret_3m": None,
        "high_52w": None, "low_52w": None, "range_position": None,
    }
    if daily is None or daily.empty or "Close" not in daily.columns:
        return out
    closes = daily["Close"].dropna().astype(float)
    if closes.empty:
        return out
    price = float(closes.iloc[-1])
    out["price"] = price
    if len(closes) >= 50:
        out["sma50"] = float(closes.rolling(50).mean().iloc[-1])
        out["above_50dma"] = price > out["sma50"]
    if len(closes) >= 200:
        out["sma200"] = float(closes.rolling(200).mean().iloc[-1])
        out["above_200dma"] = price > out["sma200"]
    out["rsi"] = rsi(closes)
    if len(closes) >= 63:
        out["ret_3m"] = (price / float(closes.iloc[-63]) - 1.0) * 100.0
    high = float(closes.max())
    low = float(closes.min())
    out["high_52w"], out["low_52w"] = high, low
    if high > low:
        out["range_position"] = (price - low) / (high - low) * 100.0
    return out


def technical_score(facts: dict) -> tuple[float, list[str]]:
    """(score 0-100, factual driver bullets). Trend, momentum, position."""
    score = 50.0
    drivers: list[str] = []

    if facts.get("above_200dma") is True:
        score += 15
        drivers.append("Price above 200DMA")
    elif facts.get("above_200dma") is False:
        score -= 15
        drivers.append("Price below 200DMA")

    if facts.get("above_50dma") is True:
        score += 8
        drivers.append("Price above 50DMA")
    elif facts.get("above_50dma") is False:
        score -= 8
        drivers.append("Price below 50DMA")

    value = facts.get("rsi")
    if value is not None:
        if 45 <= value <= 65:
            score += 10
            drivers.append(f"RSI {value:.0f} (mid-range)")
        elif value > 70:
            score += 2
            drivers.append(f"RSI {value:.0f} (elevated)")
        elif value < 30:
            score -= 10
            drivers.append(f"RSI {value:.0f} (depressed)")
        else:
            score += 4
            drivers.append(f"RSI {value:.0f}")

    ret = facts.get("ret_3m")
    if ret is not None:
        step = max(-12.0, min(12.0, ret / 2.0))
        score += step
        drivers.append(f"3-month move {ret:+.1f}%")

    pos = facts.get("range_position")
    if pos is not None:
        score += (pos - 50.0) / 10.0
        drivers.append(f"At {pos:.0f}% of 52-week range")

    return max(0.0, min(100.0, score)), drivers


def fundamental_score(info: dict) -> tuple[float, list[str]]:
    """(score 0-100, factual driver bullets). Margins, returns, leverage, growth."""
    score = 50.0
    drivers: list[str] = []

    roe = info.get("returnOnEquity")
    if roe is not None:
        pct = float(roe) * 100.0
        score += max(-12.0, min(15.0, (pct - 10.0) / 2.0))
        drivers.append(f"ROE {pct:.0f}%")

    margin = info.get("profitMargins")
    if margin is not None:
        pct = float(margin) * 100.0
        score += max(-10.0, min(12.0, (pct - 8.0) / 2.5))
        drivers.append(f"Net margin {pct:.0f}%")

    dte = info.get("debtToEquity")
    if dte is not None:
        ratio = float(dte)
        if ratio < 50:
            score += 8
            drivers.append(f"Debt/equity {ratio:.0f}% (low)")
        elif ratio < 120:
            score += 2
            drivers.append(f"Debt/equity {ratio:.0f}%")
        else:
            score -= 8
            drivers.append(f"Debt/equity {ratio:.0f}% (elevated)")

    growth = info.get("revenueGrowth")
    if growth is not None:
        pct = float(growth) * 100.0
        score += max(-10.0, min(12.0, pct / 2.0))
        drivers.append(f"Revenue growth {pct:+.0f}% YoY")

    fcf = info.get("freeCashflow")
    if fcf is not None:
        if float(fcf) > 0:
            score += 6
            drivers.append("Positive free cash flow")
        else:
            score -= 6
            drivers.append("Negative free cash flow")

    return max(0.0, min(100.0, score)), drivers


def at_a_glance(tech: dict, info: dict) -> list[tuple[str, str]]:
    """The seven neutral-language chips: (label, value). Facts only."""
    chips: list[tuple[str, str]] = []

    if tech.get("above_200dma") is True:
        chips.append(("Trend", "Above 200DMA"))
    elif tech.get("above_200dma") is False:
        chips.append(("Trend", "Below 200DMA"))
    else:
        chips.append(("Trend", "—"))

    value = tech.get("rsi")
    if value is None:
        chips.append(("Momentum", "—"))
    elif value >= 70:
        chips.append(("Momentum", f"Elevated (RSI {value:.0f})"))
    elif value >= 55:
        chips.append(("Momentum", f"Firm (RSI {value:.0f})"))
    elif value >= 45:
        chips.append(("Momentum", f"Neutral (RSI {value:.0f})"))
    elif value >= 30:
        chips.append(("Momentum", f"Soft (RSI {value:.0f})"))
    else:
        chips.append(("Momentum", f"Depressed (RSI {value:.0f})"))

    pos = tech.get("range_position")
    chips.append(("52-week range", f"At {pos:.0f}% of range" if pos is not None else "—"))

    roe = info.get("returnOnEquity")
    if roe is None:
        chips.append(("Profitability", "—"))
    else:
        pct = float(roe) * 100.0
        tier = "High" if pct >= 20 else "Moderate" if pct >= 8 else "Low"
        chips.append(("Profitability", f"{tier} (ROE {pct:.0f}%)"))

    dte = info.get("debtToEquity")
    if dte is None:
        chips.append(("Leverage", "—"))
    else:
        ratio = float(dte)
        tier = "Low" if ratio < 50 else "Moderate" if ratio < 120 else "High"
        chips.append(("Leverage", f"{tier} (D/E {ratio:.0f}%)"))

    beta = info.get("beta")
    if beta is None:
        chips.append(("Volatility", "—"))
    else:
        b = float(beta)
        rel = "Higher than market" if b > 1.15 else "Near market" if b >= 0.85 else "Lower than market"
        chips.append(("Volatility", f"{rel} (β {b:.2f})"))

    pe = info.get("trailingPE")
    if pe is None or float(pe) <= 0:
        chips.append(("Valuation", "—"))
    else:
        ratio = float(pe)
        tier = "Low multiple" if ratio < 15 else "Mid multiple" if ratio < 30 else "High multiple"
        chips.append(("Valuation", f"{tier} (P/E {ratio:.0f})"))

    return chips
