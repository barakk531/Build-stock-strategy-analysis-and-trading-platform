"""News: yfinance primary, Yahoo RSS fallback. Normalized, deduped, None-safe.

Every item is normalized to {"title", "publisher", "link", "summary", "time"}
(time = timezone-aware datetime or None). News text is untrusted third-party
content — pages render it as text and lib/claude_analyst.py quotes it as data.
"""

from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import streamlit as st
import yfinance as yf

_TICKER_RE = re.compile(r"^[A-Z0-9.\-^=]{1,12}$")
_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"


def _normalize_yf_item(item: dict) -> dict | None:
    """Handle both yfinance news shapes (flat legacy, nested 'content')."""
    try:
        content = item.get("content") if isinstance(item.get("content"), dict) else item
        title = content.get("title")
        if not title:
            return None
        when = None
        raw_time = content.get("pubDate") or content.get("displayTime")
        if raw_time:
            try:
                when = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            except ValueError:
                when = None
        if when is None and item.get("providerPublishTime"):
            when = datetime.fromtimestamp(int(item["providerPublishTime"]), tz=timezone.utc)
        provider = content.get("provider") or {}
        publisher = (provider.get("displayName") if isinstance(provider, dict) else None) or item.get("publisher")
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = (url_obj.get("url") if isinstance(url_obj, dict) else None) or item.get("link")
        return {
            "title": str(title).strip(),
            "publisher": str(publisher).strip() if publisher else "Yahoo Finance",
            "link": link,
            "summary": str(content.get("summary") or content.get("description") or "").strip(),
            "time": when,
        }
    except Exception:
        return None


def _rss_items(ticker: str, limit: int = 10) -> list[dict]:
    """Yahoo RSS fallback, stdlib-only parse. https only, small and bounded."""
    if not _TICKER_RE.match(ticker):
        return []
    url = _RSS_URL.format(t=urllib.request.quote(ticker))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (market-analyst)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(1_000_000)
        root = ET.fromstring(raw)
        items = []
        for node in root.iter("item"):
            title = (node.findtext("title") or "").strip()
            if not title:
                continue
            when = None
            pub = node.findtext("pubDate")
            if pub:
                try:
                    when = parsedate_to_datetime(pub)
                except (TypeError, ValueError):
                    when = None
            items.append({
                "title": title,
                "publisher": "Yahoo Finance",
                "link": (node.findtext("link") or "").strip() or None,
                "summary": (node.findtext("description") or "").strip(),
                "time": when,
            })
            if len(items) >= limit:
                break
        return items
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def ticker_news(ticker: str, limit: int = 12) -> list[dict]:
    """News for one symbol: yfinance first, RSS fallback. Newest first."""
    ticker = (ticker or "").upper().strip()
    if not _TICKER_RE.match(ticker):
        return []
    items: list[dict] = []
    try:
        for raw in (yf.Ticker(ticker).news or [])[: limit * 2]:
            normalized = _normalize_yf_item(raw)
            if normalized:
                items.append(normalized)
    except Exception:
        pass
    if not items:
        items = _rss_items(ticker, limit)
    seen: set[str] = set()
    unique = []
    for item in items:
        key = item["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda i: i["time"] or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    return unique[:limit]


@st.cache_data(ttl=600, show_spinner=False)
def market_news(limit: int = 12, hours: int = 24) -> list[dict]:
    """Aggregated market headlines from the major index feeds, last N hours."""
    pooled: list[dict] = []
    for symbol in ("^GSPC", "^DJI", "^NDX"):
        pooled.extend(ticker_news(symbol, limit))
    seen: set[str] = set()
    unique = []
    for item in pooled:
        key = item["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    fresh = [i for i in unique if i["time"] and i["time"] >= cutoff] or unique
    fresh.sort(key=lambda i: i["time"] or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    return fresh[:limit]


def safe_url(link) -> str | None:
    """Return the URL only if it is a plain http(s) link (blocks javascript:)."""
    if not link:
        return None
    text = str(link).strip()
    return text if text.lower().startswith(("http://", "https://")) else None


def safe_link(title: str, link) -> str:
    """Markdown link with an HTML-escaped title and a validated URL.

    News text is untrusted third-party content, so the title is escaped and
    the URL scheme checked before it is ever rendered — safe even under
    `unsafe_allow_html=True`.
    """
    escaped = html.escape(str(title or "").strip())
    url = safe_url(link)
    return f"[{escaped}]({url})" if url else escaped


def escape(text) -> str:
    """HTML-escape any third-party string bound for an unsafe_allow_html block."""
    return html.escape(str(text or ""))


def time_ago(when: datetime | None) -> str:
    if when is None:
        return ""
    delta = datetime.now(timezone.utc) - when.astimezone(timezone.utc)
    seconds = int(delta.total_seconds())
    if seconds < 3600:
        return f"{max(1, seconds // 60)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"
