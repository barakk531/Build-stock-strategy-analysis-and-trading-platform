from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class MarketTickerItem(BaseModel):
    symbol: str
    price: float
    change: float
    change_percent: float
    trade_date: date | None
