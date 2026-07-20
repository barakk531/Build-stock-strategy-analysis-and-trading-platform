"""ETF Analyzer — chart, returns, risk gauge, sector & holdings, cost peers."""

from __future__ import annotations

import streamlit as st

from lib.charts import VIEWS, render_gauge, render_price_chart, render_weight_bars
from lib.config import (
    APP_NAME,
    apply_chrome,
    fmt_pct,
    fmt_price,
    fmt_ratio,
    render_disclosure,
)
from lib.etf_peers import cheaper_alternatives, find_peer_group, get_expense_ratio
from lib.logos import logo_html
from lib.market_data import PERIOD_MAP, get_etf_details, get_history, get_quote
from lib.news import escape
from lib.risk import RISK_GAUGE_BANDS, risk_label, risk_score

st.set_page_config(page_title=f"ETF Analyzer · {APP_NAME}", page_icon="🧺", layout="wide")
apply_chrome(st)

st.title("🧺 ETF Analyzer")

top = st.columns([2, 3])
with top[0]:
    ticker = st.text_input("ETF ticker", value="VOO", key="etf_ticker").upper().strip()
with top[1]:
    period = st.segmented_control(
        "Chart period", options=list(PERIOD_MAP.keys()), default="1Y", key="etf_period"
    ) or "1Y"

if not ticker:
    st.info("Enter an ETF ticker to begin.")
    st.stop()

details = get_etf_details(ticker)
quote = get_quote(ticker)
chart_hist = get_history(ticker, period)
hist_3y = get_history(ticker, "3Y")

if details.get("name") is None and quote.get("price") is None and chart_hist.empty:
    st.error(f"No data found for '{ticker}'. Check the symbol and try again.")
    render_disclosure(st)
    st.stop()

name = details.get("name") or ticker
head = st.columns([0.6, 5, 2, 2])
with head[0]:
    st.markdown(logo_html(ticker, 64), unsafe_allow_html=True)
with head[1]:
    st.markdown(f"### {name}")
    st.caption(ticker + (" · ETF" if details.get("expense_ratio") is not None else ""))
head[2].metric("Price", fmt_price(quote.get("price")),
               fmt_pct(quote.get("change_pct")) if quote.get("change_pct") is not None else None)
expense = get_expense_ratio(ticker, details.get("expense_ratio"))
head[3].metric("Expense ratio", f"{expense:.2f}%" if expense is not None else "—")

# --- Chart --------------------------------------------------------------------
view = st.radio("View", VIEWS, horizontal=True, key="etf_view")
baseline = quote.get("prev_close") if period == "1D" else None
fig = render_price_chart(chart_hist, view=view, baseline_price=baseline, show_volume=True) if not chart_hist.empty else None
if fig is not None:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Price history is temporarily unavailable for this ETF.")

st.divider()

# --- Returns + risk gauge -----------------------------------------------------
ret_col, risk_col = st.columns([3, 2])
with ret_col:
    st.subheader("Returns & profile")
    rows = [
        ("YTD return", fmt_pct(details["ytd_return"] * 100) if details.get("ytd_return") is not None else "—"),
        ("3Y avg return", fmt_pct(details["three_year_return"] * 100) if details.get("three_year_return") is not None else "—"),
        ("5Y avg return", fmt_pct(details["five_year_return"] * 100) if details.get("five_year_return") is not None else "—"),
        ("3Y beta", fmt_ratio(details.get("beta3y"))),
        ("Yield", fmt_pct(details["yield"] * 100) if details.get("yield") is not None else "—"),
        ("Total assets", "—" if details.get("total_assets") is None else fmt_price(details["total_assets"]).replace(".00", "")),
    ]
    for label, value in rows:
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;padding:3px 0;"
            f"border-bottom:1px solid #2c2c2a'><span style='color:#898781'>{label}</span>"
            f"<span style='color:#c3c2b7'>{value}</span></div>",
            unsafe_allow_html=True,
        )

with risk_col:
    score, drivers = risk_score(hist_3y, details.get("top_holdings"))
    st.plotly_chart(
        render_gauge(score, "Risk score", risk_label(score), bands=RISK_GAUGE_BANDS),
        use_container_width=True, config={"displayModeBar": False},
    )
    for driver in drivers:
        st.caption(f"• {driver}")

st.divider()

# --- Sector breakdown + top holdings -----------------------------------------
sector_col, holdings_col = st.columns(2)
with sector_col:
    st.subheader("Sector breakdown")
    weights = details.get("sector_weights") or {}
    ordered = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    if ordered:
        st.plotly_chart(
            render_weight_bars([k for k, _ in ordered], [v for _, v in ordered], height=340),
            use_container_width=True, config={"displayModeBar": False},
        )
    else:
        st.caption("Sector weights are not available for this ETF.")

with holdings_col:
    st.subheader("Top holdings")
    holdings = details.get("top_holdings") or []
    if not holdings:
        st.caption("Holdings are not available for this ETF.")
    for row in holdings[:12]:
        symbol = str(row.get("symbol", ""))
        sym_esc = escape(symbol)
        name_esc = escape(row.get("name", "")[:28])
        weight = row.get("weight")
        st.markdown(
            f"<div style='display:flex;align-items:center;justify-content:space-between;padding:3px 0;"
            f"border-bottom:1px solid #2c2c2a'>"
            f"<span>{logo_html(symbol, 22)} &nbsp;<b>{sym_esc}</b> &nbsp;"
            f"<span style='color:#898781'>{name_esc}</span></span>"
            f"<span style='color:#c3c2b7'>{weight * 100:.1f}%</span></div>"
            if weight is not None else
            f"<div style='padding:3px 0'>{logo_html(symbol, 22)} &nbsp;<b>{sym_esc}</b></div>",
            unsafe_allow_html=True,
        )

st.divider()

# --- Peer comparison & cheaper alternatives ----------------------------------
st.subheader("Cost comparison")
group = find_peer_group(ticker)
if group is None:
    st.caption("No curated peer group for this ETF.")
else:
    group_name, peers = group
    st.caption(f"Peer group: **{group_name}** — compared on expense ratio (lower is cheaper).")
    peer_rows = sorted(
        ({"Ticker": p, "Expense ratio": get_expense_ratio(p)} for p in peers),
        key=lambda r: (r["Expense ratio"] is None, r["Expense ratio"] or 0),
    )
    st.dataframe(
        [{"Ticker": r["Ticker"],
          "Expense ratio": f"{r['Expense ratio']:.2f}%" if r["Expense ratio"] is not None else "—",
          "This ETF": "◀" if r["Ticker"] == ticker else ""}
         for r in peer_rows],
        use_container_width=True, hide_index=True,
    )

    alts = cheaper_alternatives(ticker, position_usd=100_000.0)
    if alts:
        best = alts[0]
        st.success(
            f"💡 On a **$100,000** position, **{best['ticker']}** would cost about "
            f"**{best['savings_bps']:.1f} bps** (${best['savings_usd']:,.0f}) less per year "
            f"than {ticker} in fund fees."
        )
    elif get_expense_ratio(ticker) is not None:
        st.caption("No cheaper peer in this group — this ETF is at or below the group's low.")

render_disclosure(st)
