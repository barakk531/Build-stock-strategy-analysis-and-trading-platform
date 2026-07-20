"""Portfolio — holdings entry, value & return, allocation, risk, AI deep-dive.

Holdings persist locally to data/portfolio.json (gitignored). This is a
personal-research tracker, not a brokerage — no orders are ever placed.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from lib.charts import render_pie
from lib.claude_analyst import available as claude_available
from lib.claude_analyst import deep_analysis_stream
from lib.config import (
    APP_NAME,
    apply_chrome,
    fmt_big,
    fmt_pct,
    fmt_price,
    render_disclosure,
)
from lib.portfolio import compute_positions, load_portfolio, remove_holding, upsert_holding
from lib.risk import risk_label, risk_score

st.set_page_config(page_title=f"Portfolio · {APP_NAME}", page_icon="💼", layout="wide")
apply_chrome(st)

st.title("💼 Portfolio")
st.caption("A local, simulated tracker for your own research. Holdings are saved to this machine only.")

# --- Editor -------------------------------------------------------------------
holdings = load_portfolio()

with st.expander("➕ Add or update a holding", expanded=not holdings):
    form = st.columns([2, 2, 2, 1])
    new_ticker = form[0].text_input("Ticker", key="pf_ticker").upper().strip()
    new_shares = form[1].number_input("Shares", min_value=0.0, step=1.0, key="pf_shares")
    new_cost = form[2].number_input("Cost basis / share", min_value=0.0, step=1.0, key="pf_cost")
    form[3].markdown("<br>", unsafe_allow_html=True)
    if form[3].button("Save", key="pf_save"):
        if upsert_holding(new_ticker, new_shares, new_cost):
            st.success(f"Saved {new_ticker}.")
            st.rerun()
        else:
            st.error("Enter a valid ticker and a positive share count.")

if not holdings:
    st.info("Add a holding above to see your portfolio value, allocation, and risk.")
    render_disclosure(st)
    st.stop()

# --- Editable table for removals ----------------------------------------------
with st.expander("Manage holdings"):
    for holding in holdings:
        row = st.columns([3, 2, 2, 1])
        row[0].markdown(f"**{holding['ticker']}**")
        row[1].caption(f"{holding['shares']:g} shares")
        row[2].caption(f"basis {fmt_price(holding['cost_basis'])}")
        if row[3].button("Remove", key=f"rm_{holding['ticker']}"):
            remove_holding(holding["ticker"])
            st.rerun()

# --- Computed positions -------------------------------------------------------
result = compute_positions(holdings)
positions = result["positions"]

m = st.columns(4)
m[0].metric("Current value", fmt_big(result["total_value"]) if result["total_value"] else "—")
m[1].metric("Total cost", fmt_big(result["total_cost"]) if result["total_cost"] else "—")
m[2].metric(
    "Total return",
    fmt_big(result["total_gain"]) if result["total_gain"] is not None else "—",
    fmt_pct(result["total_gain_pct"]) if result["total_gain_pct"] is not None else None,
)
m[3].metric("Positions", str(len(positions)))

st.divider()

# --- Allocation + sector ------------------------------------------------------
alloc_col, sector_col = st.columns(2)
with alloc_col:
    st.subheader("Allocation")
    valued = [p for p in positions if p.get("value")]
    if valued:
        valued.sort(key=lambda p: p["value"], reverse=True)
        st.plotly_chart(
            render_pie([p["ticker"] for p in valued], [p["value"] for p in valued]),
            use_container_width=True, config={"displayModeBar": False},
        )
    else:
        st.caption("Live prices are temporarily unavailable.")

with sector_col:
    st.subheader("Sector breakdown")
    sector_totals: dict[str, float] = {}
    for p in positions:
        if p.get("value"):
            sector_totals[p["sector"]] = sector_totals.get(p["sector"], 0.0) + p["value"]
    if sector_totals:
        ordered = sorted(sector_totals.items(), key=lambda kv: kv[1], reverse=True)
        st.plotly_chart(
            render_pie([k for k, _ in ordered], [v for _, v in ordered]),
            use_container_width=True, config={"displayModeBar": False},
        )
    else:
        st.caption("Sector data is temporarily unavailable.")

st.divider()

# --- Holdings table -----------------------------------------------------------
st.subheader("Holdings")
table = []
for p in positions:
    table.append({
        "Ticker": p["ticker"],
        "Name": (p.get("name") or "")[:28],
        "Shares": f"{p['shares']:g}",
        "Price": fmt_price(p.get("price")),
        "Value": fmt_price(p.get("value")) if p.get("value") is not None else "—",
        "Weight": f"{p['weight']:.1f}%" if p.get("weight") is not None else "—",
        "Return": fmt_pct(p["gain_pct"]) if p.get("gain_pct") is not None else "—",
    })
st.dataframe(table, use_container_width=True, hide_index=True)

# --- Portfolio risk -----------------------------------------------------------
st.divider()
risk_col, ai_col = st.columns([2, 3])
with risk_col:
    st.subheader("Portfolio risk")
    # Weight-blended synthetic price path from each holding's 3Y history.
    from lib.market_data import get_history_bulk

    tickers = tuple(p["ticker"] for p in valued) if valued else ()
    weights = {p["ticker"]: (p["weight"] or 0) / 100.0 for p in valued}
    hist = get_history_bulk(tickers, "3Y") if tickers else {}
    norms = {}
    for ticker, frame in hist.items():
        if frame is None or frame.empty or "Close" not in frame:
            continue
        base = frame["Close"].iloc[0]
        if base:
            norms[ticker] = frame["Close"] / base * weights.get(ticker, 0)
    # Align on common dates (dropna) rather than fill_value=0, so a holiday one
    # ticker is missing doesn't create an artificial dip in the blended path.
    blended = pd.DataFrame(norms).dropna().sum(axis=1) if norms else None
    if blended is not None and len(blended) > 10:
        score, drivers = risk_score(pd.DataFrame({"Close": blended}))
        from lib.charts import render_gauge
        from lib.risk import RISK_GAUGE_BANDS

        st.plotly_chart(
            render_gauge(score, "Risk score", risk_label(score), bands=RISK_GAUGE_BANDS),
            use_container_width=True, config={"displayModeBar": False},
        )
        for driver in drivers:
            st.caption(f"• {driver}")
    else:
        st.caption("Not enough history to score portfolio risk.")

with ai_col:
    st.subheader("AI deep analysis")
    if not claude_available():
        st.info("Set `ANTHROPIC_API_KEY` in `.env` to enable AI analysis (optional).")
    elif st.button("Analyze my portfolio", key="btn_pf"):
        facts = {
            "total_value": result["total_value"],
            "total_return_pct": result["total_gain_pct"],
            "positions": [
                {"ticker": p["ticker"], "weight_pct": p.get("weight"),
                 "sector": p.get("sector"), "return_pct": p.get("gain_pct")}
                for p in positions
            ],
            "sector_weights": {
                k: round(v / result["total_value"] * 100, 1)
                for k, v in sector_totals.items()
            } if result["total_value"] else {},
        }
        st.write_stream(deep_analysis_stream("this portfolio", "This portfolio", facts))

render_disclosure(st)
