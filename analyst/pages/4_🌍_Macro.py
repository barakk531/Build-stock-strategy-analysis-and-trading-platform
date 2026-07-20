"""Macro — FRED indicators, yield curve, and a Claude macro pulse-check."""

from __future__ import annotations

import streamlit as st

from lib.charts import render_line
from lib.claude_analyst import available as claude_available
from lib.claude_analyst import macro_pulse_stream
from lib.config import APP_NAME, apply_chrome, render_disclosure
from lib.macro import INDICATORS, all_snapshots, fred_available
from lib.rates import yield_curve

st.set_page_config(page_title=f"Macro · {APP_NAME}", page_icon="🌍", layout="wide")
apply_chrome(st)

st.title("🌍 Macro")

if not fred_available():
    st.warning(
        "FRED data needs a free API key. Add `FRED_API_KEY` to your `.env` "
        "(get one at https://fred.stlouisfed.org/docs/api/api_key.html). "
        "The rest of the dashboard works without it."
    )
    render_disclosure(st)
    st.stop()

# --- Indicator tiles ----------------------------------------------------------
st.subheader("Key indicators")
snapshots = all_snapshots()
tiles = st.columns(4)
for i, (series_id, snap) in enumerate(snapshots.items()):
    _, unit, _ = INDICATORS[series_id]
    value = snap.get("value")
    prev = snap.get("prev")
    delta = None
    if value is not None and prev is not None:
        delta = f"{value - prev:+.2f} {unit}"
    display = f"{value:,.2f} {unit}" if value is not None else "—"
    tiles[i % 4].metric(snap["label"], display, delta)

st.divider()

# --- Yield curve --------------------------------------------------------------
st.subheader("Treasury yield curve")
curve = yield_curve()
if curve:
    labels = [c[0] for c in curve]
    values = [c[1] for c in curve]
    st.plotly_chart(
        render_line(labels, values, height=340, suffix="%", markers=True),
        use_container_width=True, config={"displayModeBar": False},
    )
    inverted = len(values) >= 2 and values[0] > values[-1]
    st.caption(
        "The curve is currently **inverted** (short rates above long rates)."
        if inverted else
        "The curve currently slopes **upward** (long rates above short rates)."
    )
else:
    st.caption("Yield curve data is temporarily unavailable.")

st.divider()

# --- Claude macro pulse-check -------------------------------------------------
st.subheader("Macro pulse-check")
if not claude_available():
    st.info("Set `ANTHROPIC_API_KEY` in `.env` to enable the AI pulse-check (optional).")
elif st.button("Generate macro pulse-check", key="btn_macro"):
    payload = {
        series_id: {"label": snap["label"], "value": snap["value"], "previous": snap["prev"]}
        for series_id, snap in snapshots.items()
        if snap.get("value") is not None
    }
    st.write_stream(macro_pulse_stream(payload))

render_disclosure(st)
