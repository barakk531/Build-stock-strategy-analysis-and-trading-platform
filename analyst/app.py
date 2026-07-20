"""Stock Market Analyst — landing page with a quick market snapshot.

Educational and personal-research use only. Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from lib.config import APP_NAME, apply_chrome, fmt_pct, fmt_price, render_disclosure
from lib.market_data import INDEX_TICKERS, get_history_bulk, get_quotes_bulk
from lib.news import market_news, safe_link, time_ago

st.set_page_config(page_title=APP_NAME, page_icon="📈", layout="wide")
apply_chrome(st)

st.title("📈 Stock Market Analyst")
st.caption("A personal, educational dashboard for market research — not investment advice.")

# --- Quick snapshot: the six headline indices/assets --------------------------
HEADLINE = ["^GSPC", "^NDX", "^DJI", "^RUT", "^VIX", "^TNX"]
quotes = get_quotes_bulk(tuple(HEADLINE))

cols = st.columns(len(HEADLINE))
for col, ticker in zip(cols, HEADLINE):
    quote = quotes.get(ticker, {})
    price = quote.get("price")
    change_pct = quote.get("change_pct")
    with col:
        st.metric(
            label=INDEX_TICKERS.get(ticker, ticker),
            value=fmt_price(price) if price is not None else "—",
            delta=fmt_pct(change_pct) if change_pct is not None else None,
        )

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("S&P 500 — last 6 months")
    from lib.charts import render_price_chart

    history = get_history_bulk(("^GSPC",), "6M").get("^GSPC")
    fig = render_price_chart(history, view="Area") if history is not None else None
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Market data is temporarily unavailable — try refreshing.")

    st.markdown(
        "**Explore the dashboard** using the sidebar: "
        "**Market Pulse** for the full board, **Stock Analyzer** for a single "
        "name, **ETF Analyzer**, **Macro**, **Portfolio**, and **News**."
    )

with right:
    st.subheader("Top headlines")
    headlines = market_news(limit=6)
    if not headlines:
        st.caption("No recent headlines available.")
    for item in headlines:
        ago = time_ago(item.get("time"))
        st.markdown(f"**{safe_link(item['title'], item.get('link'))}**")
        meta = " · ".join(x for x in (item.get("publisher"), ago) if x)
        st.caption(meta)

render_disclosure(st)
