"""FRED macro indicators (fredapi). Requires FRED_API_KEY; degrades politely.

Each indicator is defined once in INDICATORS with how to present it — either
the latest level or a year-over-year change computed from the raw series.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from lib.config import fred_api_key

# series_id -> (label, unit, mode). mode: "level" | "yoy"
INDICATORS: dict[str, tuple[str, str, str]] = {
    "GDP": ("GDP (nominal, quarterly)", "$B", "level"),
    "UNRATE": ("Unemployment rate", "%", "level"),
    "CPIAUCSL": ("CPI (YoY)", "%", "yoy"),
    "CPILFESL": ("Core CPI (YoY)", "%", "yoy"),
    "FEDFUNDS": ("Fed funds rate", "%", "level"),
    "T10Y2Y": ("10Y-2Y spread", "pp", "level"),
    "RSAFS": ("Retail sales (YoY)", "%", "yoy"),
    "INDPRO": ("Industrial production (YoY)", "%", "yoy"),
}


def fred_available() -> bool:
    return fred_api_key() is not None


@st.cache_data(ttl=3600, show_spinner=False)
def get_series(series_id: str, years: int = 15) -> pd.Series:
    """Raw FRED series (last N years). Empty series when unavailable."""
    key = fred_api_key()
    if not key:
        return pd.Series(dtype=float)
    try:
        from fredapi import Fred

        start = pd.Timestamp.today() - pd.DateOffset(years=years)
        series = Fred(api_key=key).get_series(series_id, observation_start=start)
        return series.dropna() if series is not None else pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)


def indicator_snapshot(series_id: str) -> dict:
    """{"label","unit","value","prev","time"} for one INDICATORS entry."""
    label, unit, mode = INDICATORS[series_id]
    out = {"label": label, "unit": unit, "value": None, "prev": None, "time": None}
    series = get_series(series_id)
    if series.empty:
        return out
    try:
        if mode == "yoy":
            yoy = (series / series.shift(12) - 1.0) * 100.0
            yoy = yoy.dropna()
            if yoy.empty:
                return out
            out["value"] = float(yoy.iloc[-1])
            out["prev"] = float(yoy.iloc[-2]) if len(yoy) > 1 else None
            out["time"] = yoy.index[-1]
        else:
            out["value"] = float(series.iloc[-1])
            out["prev"] = float(series.iloc[-2]) if len(series) > 1 else None
            out["time"] = series.index[-1]
    except Exception:
        pass
    return out


def all_snapshots() -> dict[str, dict]:
    return {sid: indicator_snapshot(sid) for sid in INDICATORS}
