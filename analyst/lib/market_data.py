"""yfinance wrappers with Streamlit caching.

Everything network-facing is wrapped in try/except and returns None-safe
structures — a missing field or a Yahoo hiccup must degrade a widget, never
crash a page. Quotes cache for 60s, history for 300s, slow metadata longer.

Real indices (not ETF proxies) are used for market charts — see INDEX_TICKERS.
"""

from __future__ import annotations

import math
import re
import time
import urllib.parse

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# OS trust store for TLS behind AV/proxy inspection (idempotent; also done in
# lib.config, but market_data may be imported first, e.g. in tests).
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

# Yahoo's public chart endpoint needs no crumb, so it keeps working when the
# crumb endpoint is rate-limited (429) — which otherwise breaks yfinance
# wholesale. We use it directly for quotes/history and fall back to yfinance.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_session = requests.Session()
_session.headers["User-Agent"] = _UA
_CHART_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
_STANDARD_RANGES = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}

# --- Universe constants -------------------------------------------------------

# Real indices / assets for the Market Pulse grid (order = display order).
INDEX_TICKERS: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100",
    "^DJI": "Dow Jones",
    "^RUT": "Russell 2000",
    "^VIX": "VIX",
    "^TNX": "10Y Yield",
    "GC=F": "Gold",
    "CL=F": "Crude WTI",
    "BTC-USD": "Bitcoin",
    "DX-Y.NYB": "US Dollar",
}

# The 11 SPDR sector ETFs for the sector heatmap.
SECTOR_ETFS: dict[str, str] = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLV": "Health Care",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLY": "Cons. Discretionary",
    "XLP": "Cons. Staples",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "XLC": "Communication",
}

# Period label -> (yfinance period, interval). Intervals respect Yahoo's
# lookback limits (5m: 60d, 30m: 60d, 1h: 730d).
PERIOD_MAP: dict[str, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "5D": ("5d", "30m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "YTD": ("ytd", "1d"),
    "1Y": ("1y", "1d"),
    "3Y": ("3y", "1wk"),
    "5Y": ("5y", "1wk"),
    "10Y": ("10y", "1wk"),
    "20Y": ("20y", "1mo"),
    "30Y": ("30y", "1mo"),
    "Max": ("max", "1mo"),
}


def _f(value) -> float | None:
    """Coerce to finite float or None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _chart_result(symbol: str, period: str, interval: str) -> dict | None:
    """One symbol's payload from Yahoo's crumbless chart endpoint, or None.

    Standard Yahoo ranges use `range=`; non-standard windows (3y/20y/30y) use
    `period1`/`period2` epoch bounds so any lookback works.
    """
    path = urllib.parse.quote(symbol, safe="")
    params = {"interval": interval, "includePrePost": "false"}
    if period in _STANDARD_RANGES:
        params["range"] = period
    else:
        match = re.match(r"(\d+)y", period)
        years = int(match.group(1)) if match else 5
        now = int(time.time())
        params["period2"] = now
        params["period1"] = now - years * 366 * 24 * 3600
    for host in _CHART_HOSTS:
        try:
            resp = _session.get(f"{host}/v8/finance/chart/{path}", params=params, timeout=10)
            if resp.status_code != 200:
                continue
            result = (resp.json().get("chart") or {}).get("result")
            if result:
                return result[0]
        except Exception:
            continue
    return None


def _chart_df(result: dict) -> pd.DataFrame:
    """Chart payload -> OHLCV frame (Close = adjusted close, like auto_adjust)."""
    try:
        stamps = result.get("timestamp") or []
        indicators = result.get("indicators", {})
        quote = (indicators.get("quote") or [{}])[0]
        if not stamps or not quote:
            return pd.DataFrame()
        index = pd.to_datetime(stamps, unit="s", utc=True).tz_convert("America/New_York")
        df = pd.DataFrame(
            {
                "Open": quote.get("open"),
                "High": quote.get("high"),
                "Low": quote.get("low"),
                "Close": quote.get("close"),
                "Volume": quote.get("volume"),
            },
            index=index,
        )
        adj = (indicators.get("adjclose") or [{}])[0].get("adjclose")
        if adj is not None:
            df["Close"] = adj
        return df.dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


# --- Quotes -------------------------------------------------------------------


@st.cache_data(ttl=60, show_spinner=False)
def get_quote(ticker: str) -> dict:
    """Last price, previous close, day change — from fast_info (cheap).

    Returns {"ticker", "price", "prev_close", "change", "change_pct"} with
    None values on failure.
    """
    out = {
        "ticker": ticker, "price": None, "prev_close": None, "change": None,
        "change_pct": None, "volume": None, "dollar_volume": None,
    }
    # Primary: crumbless chart meta.
    meta = (_chart_result(ticker, "1d", "1d") or {}).get("meta") or {}
    price = _f(meta.get("regularMarketPrice"))
    prev = _f(meta.get("chartPreviousClose") or meta.get("previousClose"))
    volume = _f(meta.get("regularMarketVolume"))
    # Fallback: yfinance fast_info (works when the crumb limit is clear).
    if price is None:
        try:
            info = yf.Ticker(ticker).fast_info
            price = _f(getattr(info, "last_price", None))
            prev = prev if prev is not None else _f(getattr(info, "previous_close", None))
            volume = volume if volume is not None else _f(getattr(info, "last_volume", None))
        except Exception:
            pass
    out["price"] = price
    out["prev_close"] = prev
    out["volume"] = volume
    if price is not None and volume is not None:
        out["dollar_volume"] = price * volume
    if price is not None and prev not in (None, 0.0):
        out["change"] = price - prev
        out["change_pct"] = (price / prev - 1.0) * 100.0
    return out


@st.cache_data(ttl=60, show_spinner=False)
def get_quotes_bulk(tickers: tuple[str, ...]) -> dict[str, dict]:
    """get_quote for many tickers. Tuple arg so the cache key is hashable."""
    return {t: get_quote(t) for t in tickers}


# --- History ------------------------------------------------------------------


@st.cache_data(ttl=300, show_spinner=False)
def get_history(ticker: str, period_label: str) -> pd.DataFrame:
    """OHLCV history for a PERIOD_MAP label. Empty DataFrame on failure."""
    period, interval = PERIOD_MAP.get(period_label, ("1y", "1d"))
    # Primary: crumbless chart endpoint.
    result = _chart_result(ticker, period, interval)
    df = _chart_df(result) if result else pd.DataFrame()
    if not df.empty:
        return df
    # Fallback: yfinance (works when the crumb limit is clear).
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=True)
        return df.dropna(subset=["Close"]) if df is not None and not df.empty else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def get_history_bulk(tickers: tuple[str, ...], period_label: str) -> dict[str, pd.DataFrame]:
    """History per ticker (each via the crumbless chart endpoint)."""
    return {t: get_history(t, period_label) for t in tickers}


# --- Metadata -----------------------------------------------------------------


@st.cache_data(ttl=900, show_spinner=False)
def get_stock_fundamentals(ticker: str) -> dict:
    """Curated .info subset for the Stock Analyzer. All values None-safe."""
    fields = {
        "shortName": None, "longName": None, "sector": None, "industry": None,
        "marketCap": None, "trailingPE": None, "forwardPE": None, "priceToBook": None,
        "priceToSalesTrailing12Months": None, "pegRatio": None, "beta": None,
        "profitMargins": None, "grossMargins": None, "operatingMargins": None,
        "returnOnEquity": None, "returnOnAssets": None, "debtToEquity": None,
        "currentRatio": None, "quickRatio": None, "revenueGrowth": None,
        "earningsGrowth": None, "totalRevenue": None, "freeCashflow": None,
        "dividendYield": None, "payoutRatio": None, "fiftyTwoWeekHigh": None,
        "fiftyTwoWeekLow": None, "averageVolume": None, "sharesOutstanding": None,
        "targetMeanPrice": None, "recommendationKey": None,
        "numberOfAnalystOpinions": None, "longBusinessSummary": None, "website": None,
    }
    try:
        info = yf.Ticker(ticker).get_info() or {}
        for key in fields:
            fields[key] = info.get(key)
    except Exception:
        pass
    fields["ticker"] = ticker
    return fields


@st.cache_data(ttl=900, show_spinner=False)
def get_etf_details(ticker: str) -> dict:
    """ETF metadata: description, expense ratio, sector weights, top holdings.

    Shapes: sector_weights {name: fraction}, top_holdings
    [{"symbol", "name", "weight"}]. Everything optional.
    """
    out = {
        "ticker": ticker, "name": None, "description": None, "expense_ratio": None,
        "yield": None, "total_assets": None, "beta3y": None,
        "ytd_return": None, "three_year_return": None, "five_year_return": None,
        "sector_weights": {}, "top_holdings": [],
    }
    try:
        tk = yf.Ticker(ticker)
        info = tk.get_info() or {}
        out["name"] = info.get("shortName") or info.get("longName")
        out["description"] = info.get("longBusinessSummary")
        out["expense_ratio"] = _f(info.get("netExpenseRatio"))
        out["yield"] = _f(info.get("yield") or info.get("dividendYield"))
        out["total_assets"] = _f(info.get("totalAssets"))
        out["beta3y"] = _f(info.get("beta3Year") or info.get("beta"))
        out["ytd_return"] = _f(info.get("ytdReturn"))
        out["three_year_return"] = _f(info.get("threeYearAverageReturn"))
        out["five_year_return"] = _f(info.get("fiveYearAverageReturn"))

        funds = getattr(tk, "funds_data", None)
        if funds is not None:
            try:
                weights = funds.sector_weightings or {}
                out["sector_weights"] = {
                    str(k).replace("_", " ").title(): _f(v)
                    for k, v in weights.items() if _f(v)
                }
            except Exception:
                pass
            try:
                th = funds.top_holdings  # DataFrame indexed by symbol
                if th is not None and not th.empty:
                    name_col = "Name" if "Name" in th.columns else th.columns[0]
                    weight_col = "Holding Percent" if "Holding Percent" in th.columns else th.columns[-1]
                    out["top_holdings"] = [
                        {"symbol": str(sym), "name": str(row.get(name_col, sym)),
                         "weight": _f(row.get(weight_col))}
                        for sym, row in th.iterrows()
                    ]
            except Exception:
                pass
            if out["description"] is None:
                try:
                    out["description"] = funds.description
                except Exception:
                    pass
    except Exception:
        pass
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def is_etf(ticker: str) -> bool:
    """Best-effort quote-type check (ETF vs equity)."""
    try:
        info = yf.Ticker(ticker).get_info() or {}
        return str(info.get("quoteType", "")).upper() == "ETF"
    except Exception:
        return False
