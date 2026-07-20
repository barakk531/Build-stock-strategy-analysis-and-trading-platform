"""Treasury yield curve from FRED daily constant-maturity series."""

from __future__ import annotations

import streamlit as st

from lib.macro import get_series

# Maturity label -> FRED series, in curve order.
CURVE_SERIES: dict[str, str] = {
    "1M": "DGS1MO", "3M": "DGS3MO", "6M": "DGS6MO",
    "1Y": "DGS1", "2Y": "DGS2", "3Y": "DGS3", "5Y": "DGS5",
    "7Y": "DGS7", "10Y": "DGS10", "20Y": "DGS20", "30Y": "DGS30",
}


@st.cache_data(ttl=3600, show_spinner=False)
def yield_curve() -> list[tuple[str, float]]:
    """[(maturity_label, latest_yield_pct)] — empty list if FRED unavailable."""
    points: list[tuple[str, float]] = []
    for label, series_id in CURVE_SERIES.items():
        series = get_series(series_id, years=2)
        if not series.empty:
            try:
                points.append((label, float(series.iloc[-1])))
            except Exception:
                continue
    return points
