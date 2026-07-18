from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ScannerRow(BaseModel):
    symbol: str
    company_name: str | None
    sector: str | None
    industry: str | None
    market_cap: int | None
    trade_date: date | None
    close: float | None
    adjusted_close: float | None
    change_pct: float | None
    volume: float | None
    sma_20: float | None
    sma_50: float | None
    sma_150: float | None
    sma_150_slope: float | None
    average_volume: float | None
    volume_ratio: float | None
    distance_sma_150_pct: float | None
    buy_state: bool
    sell_state: bool
    latest_signal_type: str | None
    latest_signal_date: date | None


class ScannerOut(BaseModel):
    items: list[ScannerRow]
    total: int
    limit: int
    offset: int
    sectors: list[str]
