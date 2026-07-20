"""Stock Analyzer — chart, descriptive Snapshot gauges, key stats, AI analysis.

Compliance: the Snapshot shows factual scores ("Technical strength",
"Fundamental quality") and neutral chips — never buy/sell/hold language.
"""

from __future__ import annotations

import streamlit as st

from lib.charts import VIEWS, render_gauge, render_price_chart
from lib.claude_analyst import available as claude_available
from lib.claude_analyst import bull_bear_stream, deep_analysis_stream
from lib.config import (
    APP_NAME,
    apply_chrome,
    fmt_big,
    fmt_pct,
    fmt_price,
    fmt_ratio,
    render_disclosure,
)
from lib.logos import logo_html
from lib.market_data import PERIOD_MAP, get_history, get_quote, get_stock_fundamentals
from lib.news import safe_link, ticker_news, time_ago
from lib.signals import (
    at_a_glance,
    fundamental_score,
    technical_facts,
    technical_score,
)

st.set_page_config(page_title=f"Stock Analyzer · {APP_NAME}", page_icon="🔍", layout="wide")
apply_chrome(st)

st.title("🔍 Stock Analyzer")

top = st.columns([2, 3])
with top[0]:
    ticker = st.text_input("Ticker", value="AAPL", key="analyzer_ticker").upper().strip()
with top[1]:
    period = st.segmented_control(
        "Chart period", options=list(PERIOD_MAP.keys()), default="1Y", key="analyzer_period"
    ) or "1Y"

if not ticker:
    st.info("Enter a ticker symbol to begin.")
    st.stop()

info = get_stock_fundamentals(ticker)
quote = get_quote(ticker)
chart_hist = get_history(ticker, period)
daily_1y = get_history(ticker, "1Y")

if (info.get("shortName") is None and quote.get("price") is None and chart_hist.empty):
    st.error(f"No data found for '{ticker}'. Check the symbol and try again.")
    render_disclosure(st)
    st.stop()

# --- Header -------------------------------------------------------------------
name = info.get("shortName") or info.get("longName") or ticker
head = st.columns([0.6, 4, 2, 2, 2, 2])
with head[0]:
    st.markdown(logo_html(ticker, 64), unsafe_allow_html=True)
with head[1]:
    st.markdown(f"### {name}")
    sub = " · ".join(x for x in (ticker, info.get("sector"), info.get("industry")) if x)
    st.caption(sub)
price = quote.get("price")
head[2].metric("Price", fmt_price(price), fmt_pct(quote.get("change_pct")) if quote.get("change_pct") is not None else None)
head[3].metric("Market cap", fmt_big(info.get("marketCap")))
head[4].metric("Trailing P/E", fmt_ratio(info.get("trailingPE")))
head[5].metric("Beta", fmt_ratio(info.get("beta")))

# --- Main chart ---------------------------------------------------------------
view = st.radio("View", VIEWS, horizontal=True, key="analyzer_view")
baseline = quote.get("prev_close") if period == "1D" else None
fig = render_price_chart(chart_hist, view=view, baseline_price=baseline, show_volume=True) if not chart_hist.empty else None
if fig is not None:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Price history is temporarily unavailable for this symbol.")

st.divider()

# --- Snapshot -----------------------------------------------------------------
st.subheader("Snapshot")
st.caption(
    "Descriptive, factual scores — not recommendations. Technical strength "
    "summarizes trend, momentum, and position vs moving averages; Fundamental "
    "quality summarizes margins, returns, leverage, and growth."
)

tech = technical_facts(daily_1y)
tech_val, tech_drivers = technical_score(tech)
fund_val, fund_drivers = fundamental_score(info)

glance_col, tech_col, fund_col = st.columns([2, 2, 2])

with glance_col:
    st.markdown("**At a glance**")
    for label, value in at_a_glance(tech, info):
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;padding:3px 0;"
            f"border-bottom:1px solid #2c2c2a'><span style='color:#898781'>{label}</span>"
            f"<span style='color:#c3c2b7'>{value}</span></div>",
            unsafe_allow_html=True,
        )

with tech_col:
    st.plotly_chart(
        render_gauge(tech_val, "Technical strength", "Trend, momentum, position vs averages"),
        use_container_width=True, config={"displayModeBar": False},
    )
    for driver in tech_drivers:
        st.markdown(f"- {driver}")

with fund_col:
    st.plotly_chart(
        render_gauge(fund_val, "Fundamental quality", "Margins, returns, leverage, growth"),
        use_container_width=True, config={"displayModeBar": False},
    )
    for driver in fund_drivers:
        st.markdown(f"- {driver}")

st.divider()

# --- Key statistics grid ------------------------------------------------------
st.subheader("Key statistics")


def _stat_block(title: str, rows: list[tuple[str, str]]) -> None:
    st.markdown(f"**{title}**")
    for label, value in rows:
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;padding:2px 0'>"
            f"<span style='color:#898781'>{label}</span>"
            f"<span style='color:#c3c2b7'>{value}</span></div>",
            unsafe_allow_html=True,
        )


def _pct(value) -> str:
    return fmt_pct(float(value) * 100.0) if value is not None else "—"


grid = st.columns(3)
with grid[0]:
    _stat_block("Valuation", [
        ("Trailing P/E", fmt_ratio(info.get("trailingPE"))),
        ("Forward P/E", fmt_ratio(info.get("forwardPE"))),
        ("Price/Book", fmt_ratio(info.get("priceToBook"))),
        ("Price/Sales", fmt_ratio(info.get("priceToSalesTrailing12Months"))),
        ("PEG", fmt_ratio(info.get("pegRatio"))),
    ])
    st.markdown("")
    _stat_block("Income", [
        ("Revenue (ttm)", fmt_big(info.get("totalRevenue"))),
        ("Free cash flow", fmt_big(info.get("freeCashflow"))),
        ("Dividend yield", _pct(info.get("dividendYield")) if info.get("dividendYield") else "—"),
        ("Payout ratio", _pct(info.get("payoutRatio")) if info.get("payoutRatio") else "—"),
    ])
with grid[1]:
    _stat_block("Profitability", [
        ("Gross margin", _pct(info.get("grossMargins"))),
        ("Operating margin", _pct(info.get("operatingMargins"))),
        ("Net margin", _pct(info.get("profitMargins"))),
        ("Return on equity", _pct(info.get("returnOnEquity"))),
        ("Return on assets", _pct(info.get("returnOnAssets"))),
    ])
    st.markdown("")
    _stat_block("Analyst", [
        ("Mean target", fmt_price(info.get("targetMeanPrice"))),
        ("Opinions", str(info.get("numberOfAnalystOpinions") or "—")),
        ("Recommendation", str(info.get("recommendationKey") or "—").replace("_", " ").title()),
    ])
with grid[2]:
    _stat_block("Balance sheet", [
        ("Debt/Equity", fmt_ratio(info.get("debtToEquity"), 0) if info.get("debtToEquity") else "—"),
        ("Current ratio", fmt_ratio(info.get("currentRatio"))),
        ("Quick ratio", fmt_ratio(info.get("quickRatio"))),
        ("Revenue growth", _pct(info.get("revenueGrowth"))),
        ("Earnings growth", _pct(info.get("earningsGrowth"))),
    ])
    st.markdown("")
    _stat_block("Trading", [
        ("52-week high", fmt_price(info.get("fiftyTwoWeekHigh"))),
        ("52-week low", fmt_price(info.get("fiftyTwoWeekLow"))),
        ("Avg volume", fmt_big(info.get("averageVolume")).replace("$", "") if info.get("averageVolume") else "—"),
        ("Beta", fmt_ratio(info.get("beta"))),
    ])

# --- Business summary ---------------------------------------------------------
if info.get("longBusinessSummary"):
    with st.expander("Business summary"):
        st.write(info["longBusinessSummary"])

st.divider()

# --- AI analysis + headlines --------------------------------------------------
st.subheader("Analysis")
tab_bull, tab_deep, tab_news = st.tabs(["Bull / Bear case", "Deep analysis", "Recent headlines"])

# Facts handed to Claude (already computed; the model does no lookups).
facts = {
    "ticker": ticker, "name": name, "sector": info.get("sector"), "industry": info.get("industry"),
    "price": price, "market_cap": info.get("marketCap"),
    "trailing_pe": info.get("trailingPE"), "forward_pe": info.get("forwardPE"),
    "price_to_book": info.get("priceToBook"), "peg": info.get("pegRatio"),
    "gross_margin": info.get("grossMargins"), "operating_margin": info.get("operatingMargins"),
    "net_margin": info.get("profitMargins"), "roe": info.get("returnOnEquity"),
    "debt_to_equity": info.get("debtToEquity"), "revenue_growth": info.get("revenueGrowth"),
    "beta": info.get("beta"), "technical": tech,
    "technical_score": round(tech_val), "fundamental_score": round(fund_val),
    "52w_high": info.get("fiftyTwoWeekHigh"), "52w_low": info.get("fiftyTwoWeekLow"),
}

with tab_bull:
    if not claude_available():
        st.info("Set `ANTHROPIC_API_KEY` in `.env` to enable AI analysis (optional).")
    elif st.button("Generate bull / bear case", key="btn_bull"):
        st.write_stream(bull_bear_stream(ticker, name, facts))

with tab_deep:
    if not claude_available():
        st.info("Set `ANTHROPIC_API_KEY` in `.env` to enable AI analysis (optional).")
    elif st.button("Generate deep analysis", key="btn_deep"):
        st.write_stream(deep_analysis_stream(ticker, name, facts))

with tab_news:
    headlines = ticker_news(ticker, limit=10)
    if not headlines:
        st.caption("No recent headlines for this symbol.")
    for item in headlines:
        st.markdown(f"**{safe_link(item['title'], item.get('link'))}**")
        st.caption(" · ".join(x for x in (item.get("publisher"), time_ago(item.get("time"))) if x))

render_disclosure(st)
