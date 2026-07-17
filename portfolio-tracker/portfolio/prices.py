"""Fetching current market prices."""

from __future__ import annotations

import os

import yfinance as yf

from . import certs


class PriceError(Exception):
    """Raised when prices cannot be fetched."""


def _trust_windows_roots() -> None:
    """Point curl_cffi at the Windows trust store if TLS here is intercepted."""
    bundle = certs.ensure_bundle()
    if bundle:
        os.environ.setdefault("CURL_CA_BUNDLE", bundle)
        os.environ.setdefault("SSL_CERT_FILE", bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)


def latest(tickers: list[str]) -> dict[str, float]:
    """Return the most recent close for each ticker.

    Tickers that return no data are omitted from the result rather than raising,
    so a single delisted or mistyped symbol doesn't sink the whole report.
    """
    if not tickers:
        return {}

    _trust_windows_roots()

    data = yf.download(
        tickers,
        period="5d",
        progress=False,
        auto_adjust=True,
        group_by="ticker",
    )
    if data.empty:
        raise PriceError("No price data returned; check your connection or ticker symbols")

    out: dict[str, float] = {}
    for ticker in tickers:
        try:
            closes = data[ticker]["Close"].dropna() if len(tickers) > 1 else data["Close"].dropna()
        except KeyError:
            continue
        if not closes.empty:
            out[ticker] = float(closes.iloc[-1])
    return out
