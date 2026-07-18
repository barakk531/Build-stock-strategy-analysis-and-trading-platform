"""Scanner snapshot assembly and in-memory filter/sort.

The snapshot joins each active stock's latest price (plus previous close for
the daily change), latest default-parameter indicators, and latest signal.
Current buy/sell states use the default strategy parameters (volume multiplier
1.0, minimum slope 0) — custom-parameter states come from the strategy
evaluate endpoint instead. ~500 rows, so filtering and sorting happen in
Python after one round of set-based queries.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.daily_indicator import DailyIndicator
from app.models.daily_price import DailyPrice
from app.models.signal import Signal
from app.models.stock import Stock

_DEFAULT_VOLUME_MULTIPLIER = 1.0
_DEFAULT_MIN_SLOPE = 0.0


def _f(value) -> float | None:
    return None if value is None else float(value)


def buy_state(
    adj: float | None,
    sma_20: float | None,
    sma_50: float | None,
    sma_150: float | None,
    slope: float | None,
    volume_ratio: float | None,
) -> bool:
    values = (adj, sma_20, sma_50, sma_150, slope, volume_ratio)
    if any(v is None for v in values):
        return False
    return (
        slope >= _DEFAULT_MIN_SLOPE
        and adj > sma_150
        and sma_20 > sma_50
        and volume_ratio >= _DEFAULT_VOLUME_MULTIPLIER
    )


def sell_state(
    adj: float | None, sma_20: float | None, sma_50: float | None, sma_150: float | None
) -> bool:
    values = (adj, sma_20, sma_50, sma_150)
    if any(v is None for v in values):
        return False
    return adj < sma_150 and sma_20 < sma_50


def build_snapshot(db: Session) -> list[dict[str, Any]]:
    """One row per active stock with everything the scanner table shows."""
    # Latest two price rows per stock (latest close + previous close).
    rn = (
        func.row_number()
        .over(partition_by=DailyPrice.stock_id, order_by=DailyPrice.trade_date.desc())
        .label("rn")
    )
    windowed = select(
        DailyPrice.stock_id,
        DailyPrice.trade_date,
        DailyPrice.close,
        DailyPrice.adjusted_close,
        DailyPrice.volume,
        rn,
    ).subquery()
    price_rows = db.execute(select(windowed).where(windowed.c.rn <= 2)).all()
    latest_price: dict[int, Any] = {}
    prev_close: dict[int, float | None] = {}
    for row in price_rows:
        if row.rn == 1:
            latest_price[row.stock_id] = row
        else:
            prev_close[row.stock_id] = _f(row.adjusted_close)

    # Latest indicator row per stock (DISTINCT ON).
    indicator_rows = db.scalars(
        select(DailyIndicator)
        .distinct(DailyIndicator.stock_id)
        .order_by(DailyIndicator.stock_id, DailyIndicator.trade_date.desc())
    ).all()
    latest_indicator = {row.stock_id: row for row in indicator_rows}

    # Latest signal per stock (DISTINCT ON).
    signal_rows = db.scalars(
        select(Signal)
        .distinct(Signal.stock_id)
        .order_by(Signal.stock_id, Signal.trade_date.desc(), Signal.id.desc())
    ).all()
    latest_signal = {row.stock_id: row for row in signal_rows}

    stocks = db.scalars(
        select(Stock).where(Stock.is_active.is_(True)).order_by(Stock.symbol)
    ).all()

    snapshot: list[dict[str, Any]] = []
    for stock in stocks:
        price = latest_price.get(stock.id)
        indicator = latest_indicator.get(stock.id)
        signal = latest_signal.get(stock.id)

        adj = _f(price.adjusted_close) if price else None
        close = _f(price.close) if price else None
        previous = prev_close.get(stock.id)
        change_pct = (
            (adj / previous - 1.0) * 100.0 if adj is not None and previous else None
        )

        sma_20 = _f(indicator.sma_20) if indicator else None
        sma_50 = _f(indicator.sma_50) if indicator else None
        sma_150 = _f(indicator.sma_150) if indicator else None
        slope = _f(indicator.sma_150_slope) if indicator else None
        volume_ratio = _f(indicator.volume_ratio) if indicator else None
        average_volume = _f(indicator.average_volume) if indicator else None
        distance = (
            (adj / sma_150 - 1.0) * 100.0 if adj is not None and sma_150 else None
        )

        snapshot.append(
            {
                "symbol": stock.symbol,
                "company_name": stock.company_name,
                "sector": stock.sector,
                "industry": stock.industry,
                "market_cap": stock.market_cap,
                "trade_date": price.trade_date if price else None,
                "close": close,
                "adjusted_close": adj,
                "change_pct": change_pct,
                "volume": _f(price.volume) if price else None,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_150": sma_150,
                "sma_150_slope": slope,
                "average_volume": average_volume,
                "volume_ratio": volume_ratio,
                "distance_sma_150_pct": distance,
                "buy_state": buy_state(adj, sma_20, sma_50, sma_150, slope, volume_ratio),
                "sell_state": sell_state(adj, sma_20, sma_50, sma_150),
                "latest_signal_type": signal.signal_type if signal else None,
                "latest_signal_date": signal.trade_date if signal else None,
            }
        )
    return snapshot


def apply_filters(
    rows: list[dict],
    *,
    search: str | None = None,
    sector: str | None = None,
    buy_state_only: bool = False,
    sell_state_only: bool = False,
    signal_type: str | None = None,
    price_vs_sma150: str | None = None,  # above | below
    sma20_vs_sma50: str | None = None,  # above | below
    slope: str | None = None,  # positive | negative | flat
    min_volume_ratio: float | None = None,
    min_market_cap: int | None = None,
    max_market_cap: int | None = None,
) -> list[dict]:
    def keep(row: dict) -> bool:
        if search:
            needle = search.strip().lower()
            hay = f"{row['symbol']} {row['company_name'] or ''}".lower()
            if needle not in hay:
                return False
        if sector and (row["sector"] or "") != sector:
            return False
        if buy_state_only and not row["buy_state"]:
            return False
        if sell_state_only and not row["sell_state"]:
            return False
        if signal_type and row["latest_signal_type"] != signal_type.upper():
            return False
        if price_vs_sma150:
            adj, sma = row["adjusted_close"], row["sma_150"]
            if adj is None or sma is None:
                return False
            if price_vs_sma150 == "above" and not adj > sma:
                return False
            if price_vs_sma150 == "below" and not adj < sma:
                return False
        if sma20_vs_sma50:
            s20, s50 = row["sma_20"], row["sma_50"]
            if s20 is None or s50 is None:
                return False
            if sma20_vs_sma50 == "above" and not s20 > s50:
                return False
            if sma20_vs_sma50 == "below" and not s20 < s50:
                return False
        if slope:
            value = row["sma_150_slope"]
            if value is None:
                return False
            if slope == "positive" and not value > 0:
                return False
            if slope == "negative" and not value < 0:
                return False
            if slope == "flat" and abs(value) > 0.05:
                return False
        if min_volume_ratio is not None and (
            row["volume_ratio"] is None or row["volume_ratio"] < min_volume_ratio
        ):
            return False
        if min_market_cap is not None and (
            row["market_cap"] is None or row["market_cap"] < min_market_cap
        ):
            return False
        if max_market_cap is not None and (  # noqa: SIM103 — keep the filter chain uniform
            row["market_cap"] is None or row["market_cap"] > max_market_cap
        ):
            return False
        return True

    return [row for row in rows if keep(row)]


_SORT_KEYS = {
    "symbol",
    "market_cap",
    "close",
    "change_pct",
    "volume_ratio",
    "sma_150_slope",
    "distance_sma_150_pct",
    "latest_signal_date",
}


def sort_rows(rows: list[dict], sort: str = "symbol", order: str = "asc") -> list[dict]:
    if sort not in _SORT_KEYS:
        sort = "symbol"
    reverse = order == "desc"
    present = [r for r in rows if r.get(sort) is not None]
    missing = [r for r in rows if r.get(sort) is None]
    present.sort(key=lambda r: r[sort], reverse=reverse)
    return present + missing  # unknown values always sort last
