"""Stock selection + lightweight quotes for the scrolling market-ticker bar.

Reuses the scanner snapshot (which already computes each stock's latest close,
daily change %, and buy/sell state) so the ticker and the scanner never
diverge and we don't re-implement the price lookup.

Daily change is derived from adjusted closes (the snapshot's change_pct is
computed that way); the dollar change is reconciled with the displayed price so
price, $ change, and % change agree. Data is the latest completed daily close —
delayed, never real-time.

Market cap is not populated in the DB, so the "largest companies" slice is
approximated by a curated mega-cap seed list; the rest of the mixture comes
from buy/sell signals and the day's largest movers.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.scanner import service as scanner

# Recognizable large caps standing in for "largest by market cap" (the DB has
# no market_cap yet). Only those present and priced in the snapshot are shown.
_MEGACAPS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B",
    "JPM", "LLY", "V", "XOM", "UNH", "MA", "COST", "HD", "WMT", "NFLX", "ORCL",
]


def _change_usd(price: float, pct: float) -> float | None:
    """Dollar change reconciled with the displayed price: price - prev, where
    prev = price / (1 + pct/100). None if the percentage is degenerate."""
    denom = 1.0 + pct / 100.0
    if denom == 0:
        return None
    return price - price / denom


def get_ticker(db: Session, limit: int = 30) -> list[dict]:
    """A deduped mixture of ~`limit` stocks with lightweight quote fields.

    Selection order (a stock appears at most once): notable large caps, top
    gainers, top losers, buy-signal names, sell-signal names, then an
    alphabetical fill. A stock with unusable price/change data is skipped, not
    the whole feed.
    """
    snapshot = scanner.build_snapshot(db)
    priced = {
        row["symbol"]: row
        for row in snapshot
        if row.get("close") is not None and row.get("change_pct") is not None
    }
    if not priced:
        return []
    rows = list(priced.values())

    picked: dict[str, dict] = {}

    def add(candidates) -> None:
        for row in candidates:
            symbol = row["symbol"]
            if symbol not in picked and len(picked) < limit:
                picked[symbol] = row

    add([priced[s] for s in _MEGACAPS if s in priced][:10])
    add(sorted(rows, key=lambda r: r["change_pct"], reverse=True)[:6])  # top gainers
    add(sorted(rows, key=lambda r: r["change_pct"])[:6])                # top losers
    add([r for r in rows if r.get("buy_state")][:6])                    # buy signals
    add([r for r in rows if r.get("sell_state")][:6])                   # sell signals
    add(sorted(rows, key=lambda r: r["symbol"]))                        # fill remainder

    out: list[dict] = []
    for row in list(picked.values())[:limit]:
        price = float(row["close"])
        pct = float(row["change_pct"])
        change = _change_usd(price, pct)
        if change is None:
            continue  # skip only this stock, keep the feed working
        out.append({
            "symbol": row["symbol"],
            "price": round(price, 2),
            "change": round(change, 2),
            "change_percent": round(pct, 2),
            "trade_date": row.get("trade_date"),
        })
    return out
