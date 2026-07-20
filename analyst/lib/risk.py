"""Risk scoring (0-100): volatility + drawdown + concentration composite.

Descriptive only — the score maps to a labeled band from "Conservative" to
"Very aggressive"; it is not advice.
"""

from __future__ import annotations

import math

import pandas as pd

RISK_BANDS: list[tuple[float, float, str]] = [
    (0, 20, "Conservative"),
    (20, 40, "Moderate"),
    (40, 60, "Balanced-aggressive"),
    (60, 80, "Aggressive"),
    (80, 100, "Very aggressive"),
]

# Gauge bands: cool blue (low) -> amber -> red (high risk).
RISK_GAUGE_BANDS = [
    (0, 20, "rgba(57,135,229,0.50)"),
    (20, 40, "rgba(25,158,112,0.50)"),
    (40, 60, "rgba(201,133,0,0.50)"),
    (60, 80, "rgba(217,89,38,0.55)"),
    (80, 100, "rgba(248,113,113,0.60)"),
]


def risk_label(score: float) -> str:
    for lo, hi, label in RISK_BANDS:
        if lo <= score < hi:
            return label
    return RISK_BANDS[-1][2]


def _annualized_vol(closes: pd.Series, periods_per_year: int = 252) -> float | None:
    closes = closes.dropna().astype(float)
    if len(closes) < 30:
        return None
    returns = closes.pct_change().dropna()
    if returns.empty:
        return None
    return float(returns.std() * math.sqrt(periods_per_year) * 100.0)


def _max_drawdown(closes: pd.Series) -> float | None:
    closes = closes.dropna().astype(float)
    if len(closes) < 10:
        return None
    running_max = closes.cummax()
    drawdown = (closes / running_max - 1.0) * 100.0
    return float(drawdown.min())


def risk_components(history: pd.DataFrame, top_holdings: list[dict] | None = None) -> dict:
    """{"vol","drawdown","concentration"} raw ingredients (None-safe)."""
    out = {"vol": None, "drawdown": None, "concentration": None}
    if history is not None and not history.empty and "Close" in history.columns:
        # Weekly bars are common for 3Y windows — infer periods/yr from spacing.
        idx = history.index
        periods = 252
        if len(idx) > 2:
            try:
                days = (idx[-1] - idx[0]).days / max(1, len(idx) - 1)
                periods = 252 if days <= 2 else 52 if days <= 10 else 12
            except Exception:
                pass
        out["vol"] = _annualized_vol(history["Close"], periods)
        out["drawdown"] = _max_drawdown(history["Close"])
    if top_holdings:
        weights = [h.get("weight") for h in top_holdings if h.get("weight")]
        if weights:
            out["concentration"] = float(sum(weights[:10]) * 100.0)
    return out


def risk_score(history: pd.DataFrame, top_holdings: list[dict] | None = None) -> tuple[float, list[str]]:
    """(score 0-100, factual driver bullets)."""
    parts = risk_components(history, top_holdings)
    drivers: list[str] = []

    vol = parts["vol"]
    # 10% ann. vol ≈ bonds/broad low-vol, 20% ≈ broad equity, 35%+ ≈ high risk.
    vol_score = 50.0
    if vol is not None:
        vol_score = max(0.0, min(100.0, (vol - 5.0) * (100.0 / 35.0)))
        drivers.append(f"Annualized volatility {vol:.1f}%")

    dd = parts["drawdown"]
    dd_score = 50.0
    if dd is not None:
        dd_score = max(0.0, min(100.0, -dd * (100.0 / 60.0)))
        drivers.append(f"Max drawdown {dd:.1f}% over the window")

    conc = parts["concentration"]
    conc_score = None
    if conc is not None:
        conc_score = max(0.0, min(100.0, (conc - 10.0) * (100.0 / 70.0)))
        drivers.append(f"Top-10 holdings {conc:.0f}% of assets")

    if conc_score is None:
        score = 0.6 * vol_score + 0.4 * dd_score
    else:
        score = 0.5 * vol_score + 0.3 * dd_score + 0.2 * conc_score
    return max(0.0, min(100.0, score)), drivers
