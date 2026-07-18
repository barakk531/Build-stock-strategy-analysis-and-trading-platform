from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class StockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    yahoo_symbol: str
    company_name: str | None
    sector: str | None
    industry: str | None
    exchange: str | None
    currency: str | None
    market_cap: int | None
    is_sp500: bool
    is_active: bool
    date_added_to_index: date | None
    last_metadata_update: datetime | None
    last_price_sync: datetime | None


class StockListOut(BaseModel):
    items: list[StockOut]
    total: int
    limit: int
    offset: int


class DailyPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adjusted_close: float | None
    volume: int | None
    dividend: float
    stock_split: float


class PriceSeriesOut(BaseModel):
    symbol: str
    count: int
    prices: list[DailyPriceOut]


class SyncFailure(BaseModel):
    symbol: str
    reason: str


class UniverseSyncOut(BaseModel):
    constituents: int
    deactivated: int


class PriceSyncOut(BaseModel):
    synced: int
    rows: int
    failed: list[SyncFailure]
    as_of: str


class MetadataRefreshOut(BaseModel):
    updated: int
    failed: list[SyncFailure]


class DataHealthOut(BaseModel):
    active_stocks: int
    stocks_with_prices: int
    total_price_rows: int
    latest_trade_date: date | None
    stale_prices: int  # active stocks whose latest row is older than 5 days
    never_synced: int
