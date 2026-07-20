"""Market Pulse — indices grid, S&P chart, sector heatmap, movers, headlines."""

from __future__ import annotations

import streamlit as st

from lib.charts import VIEWS, render_change_bars, render_price_chart, render_sparkline
from lib.config import (
    APP_NAME,
    apply_chrome,
    change_color,
    fmt_pct,
    fmt_price,
    render_disclosure,
)
from lib.logos import logo_html
from lib.market_data import (
    INDEX_TICKERS,
    PERIOD_MAP,
    SECTOR_ETFS,
    get_history_bulk,
    get_quotes_bulk,
)
from lib.news import market_news, safe_link, time_ago

st.set_page_config(page_title=f"Market Pulse · {APP_NAME}", page_icon="💹", layout="wide")
apply_chrome(st)

st.title("💹 Market Pulse")

period = st.segmented_control(
    "Period", options=list(PERIOD_MAP.keys()), default="1M", key="pulse_period"
) or "1M"
is_intraday = period == "1D"

# --- Index / asset grid with sparklines --------------------------------------
tickers = tuple(INDEX_TICKERS.keys())
quotes = get_quotes_bulk(tickers)
histories = get_history_bulk(tickers, period)

st.subheader("Indices & assets")
grid = st.columns(5)
for i, ticker in enumerate(tickers):
    quote = quotes.get(ticker, {})
    hist = histories.get(ticker)
    change_pct = quote.get("change_pct")
    with grid[i % 5]:
        st.markdown(
            f"**{INDEX_TICKERS[ticker]}**  \n"
            f"{fmt_price(quote.get('price'))} "
            f"<span style='color:{change_color(change_pct)}'>{fmt_pct(change_pct)}</span>",
            unsafe_allow_html=True,
        )
        baseline = quote.get("prev_close") if is_intraday else None
        spark = render_sparkline(hist, baseline_price=baseline) if hist is not None else None
        if spark is not None:
            st.plotly_chart(spark, use_container_width=True, config={"displayModeBar": False},
                            key=f"spark_{ticker}")

st.divider()

# --- Big S&P 500 chart with view toggle --------------------------------------
chart_col, side_col = st.columns([3, 1])
with side_col:
    view = st.radio("Chart view", VIEWS, key="pulse_view")
with chart_col:
    st.subheader("S&P 500 (^GSPC)")
    sp = histories.get("^GSPC")
    baseline = quotes.get("^GSPC", {}).get("prev_close") if is_intraday else None
    fig = render_price_chart(sp, view=view, baseline_price=baseline, show_volume=True) if sp is not None else None
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("S&P 500 data is temporarily unavailable.")

st.divider()

# --- Sector heatmap (11 SPDR sector ETFs) ------------------------------------
st.subheader("Sectors")
sector_tickers = tuple(SECTOR_ETFS.keys())
sector_quotes = get_quotes_bulk(sector_tickers)
pairs = [
    (SECTOR_ETFS[t], sector_quotes.get(t, {}).get("change_pct"))
    for t in sector_tickers
    if sector_quotes.get(t, {}).get("change_pct") is not None
]
pairs.sort(key=lambda p: p[1], reverse=True)
if pairs:
    labels = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    st.plotly_chart(render_change_bars(labels, values, height=340), use_container_width=True,
                    config={"displayModeBar": False})
else:
    st.caption("Sector data is temporarily unavailable.")

st.divider()

# --- Movers: gainers / losers / most active ----------------------------------
MOVERS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "V",
    "UNH", "XOM", "LLY", "WMT", "MA", "HD", "COST", "NFLX", "AMD", "CRM",
    "ORCL", "BAC", "PFE", "KO", "PEP", "DIS", "INTC", "CVX", "MRK", "ABBV",
    "QCOM", "TXN", "CSCO", "IBM", "GE", "BA", "UBER", "PYPL", "SBUX", "NKE",
)
movers = get_quotes_bulk(MOVERS)
valued = [m for m in movers.values() if m.get("change_pct") is not None]


def _mover_row(quote: dict) -> str:
    ticker = quote["ticker"]
    change = quote.get("change_pct")
    return (
        f"{logo_html(ticker, 22)} &nbsp;<b>{ticker}</b> &nbsp;"
        f"{fmt_price(quote.get('price'))} &nbsp;"
        f"<span style='color:{change_color(change)}'>{fmt_pct(change)}</span>"
    )


gainers = sorted(valued, key=lambda q: q["change_pct"], reverse=True)[:8]
losers = sorted(valued, key=lambda q: q["change_pct"])[:8]
active = sorted(
    [m for m in movers.values() if m.get("dollar_volume")],
    key=lambda q: q["dollar_volume"], reverse=True,
)[:8]

g_col, l_col, a_col = st.columns(3)
for col, title, rows in (
    (g_col, "📈 Top gainers", gainers),
    (l_col, "📉 Top losers", losers),
    (a_col, "🔊 Most active", active),
):
    with col:
        st.markdown(f"**{title}**")
        if not rows:
            st.caption("Unavailable.")
        for quote in rows:
            st.markdown(_mover_row(quote), unsafe_allow_html=True)

st.divider()

# --- Top 3 headlines ----------------------------------------------------------
st.subheader("Latest headlines")
for item in market_news(limit=3):
    st.markdown(f"**{safe_link(item['title'], item.get('link'))}**")
    meta = " · ".join(x for x in (item.get("publisher"), time_ago(item.get("time"))) if x)
    st.caption(meta)
    if item.get("summary"):
        st.write(item["summary"][:220] + ("…" if len(item["summary"]) > 220 else ""))

render_disclosure(st)
