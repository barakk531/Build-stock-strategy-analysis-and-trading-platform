from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.services.backtesting.config import BacktestConfig

# The create request body IS the validated engine configuration.
BacktestCreateIn = BacktestConfig


class BacktestSummaryOut(BaseModel):
    """List-row view: configuration echo plus headline results when finished."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    name: str
    start_date: date
    end_date: date
    initial_cash: float
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    total_return_pct: float | None = None
    max_drawdown_pct: float | None = None
    # Not named `trades` — that would collide with the ORM relationship when
    # validating from attributes.
    trades_count: int | None = None


class BacktestListOut(BaseModel):
    items: list[BacktestSummaryOut]
    total: int
    limit: int
    offset: int


class BacktestDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    name: str
    parameters_json: dict
    parameter_hash: str
    universe_json: dict
    settings_json: dict
    commission_model_json: dict
    slippage_model_json: dict
    start_date: date
    end_date: date
    initial_cash: float
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    results_json: dict | None
    created_at: datetime


class BacktestTradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    quantity: float
    entry_signal_date: date
    entry_date: date
    entry_price: float
    exit_signal_date: date | None
    exit_date: date | None
    exit_price: float | None
    commission_paid: float
    pnl: float | None
    pnl_percent: float | None
    holding_days: int | None
    status: str


class BacktestTradeListOut(BaseModel):
    items: list[BacktestTradeOut]
    total: int
    limit: int
    offset: int


class BacktestSkipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    signal_date: date
    signal_type: str
    reason: str
    detail: str | None


class BacktestSkipListOut(BaseModel):
    items: list[BacktestSkipOut]
    total: int
    limit: int
    offset: int
