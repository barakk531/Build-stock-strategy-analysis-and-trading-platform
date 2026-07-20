"""News — aggregated market headlines and by-ticker search."""

from __future__ import annotations

import streamlit as st

from lib.config import APP_NAME, apply_chrome, render_disclosure
from lib.logos import logo_html
from lib.news import market_news, safe_link, ticker_news, time_ago

st.set_page_config(page_title=f"News · {APP_NAME}", page_icon="📰", layout="wide")
apply_chrome(st)

st.title("📰 News")


def _render_item(item: dict, ticker: str | None = None) -> None:
    # Logo (trusted, validated HTML) and heading (untrusted, escaped markdown)
    # are rendered separately so third-party text never enters an HTML block.
    if ticker:
        badge_col, text_col = st.columns([0.06, 1])
        badge_col.markdown(logo_html(ticker, 22), unsafe_allow_html=True)
        body = text_col
    else:
        body = st
    body.markdown(f"**{safe_link(item['title'], item.get('link'))}**")
    meta = " · ".join(x for x in (item.get("publisher"), time_ago(item.get("time"))) if x)
    body.caption(meta)
    summary = item.get("summary")
    if summary:
        body.write(summary[:280] + ("…" if len(summary) > 280 else ""))
    st.divider()


tab_market, tab_ticker = st.tabs(["Market headlines", "By ticker"])

with tab_market:
    st.caption("Aggregated from the major U.S. index feeds.")
    headlines = market_news(limit=20, hours=48)
    if not headlines:
        st.info("No recent headlines available.")
    for item in headlines:
        _render_item(item)

with tab_ticker:
    ticker = st.text_input("Search a ticker", value="AAPL", key="news_ticker").upper().strip()
    if ticker:
        items = ticker_news(ticker, limit=20)
        if not items:
            st.info(f"No recent headlines for '{ticker}'.")
        for item in items:
            _render_item(item, ticker=ticker)

render_disclosure(st)
