from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.stock import SyncFailure


class DailyIndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trade_date: date
    sma_20: float | None
    sma_50: float | None
    sma_150: float | None
    average_volume: float | None
    volume_ratio: float | None
    sma_150_slope: float | None


class IndicatorSeriesOut(BaseModel):
    symbol: str
    count: int
    indicators: list[DailyIndicatorOut]


class ConditionOut(BaseModel):
    key: str
    label: str
    passed: bool
    actual: float | None
    threshold: float | None
    comparison: str


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_id: int
    strategy_id: int
    trade_date: date
    signal_type: str
    execution_date: date | None
    reference_price: float | None
    conditions_json: dict
    parameter_snapshot_json: dict
    created_at: datetime


class SignalListOut(BaseModel):
    items: list[SignalOut]
    count: int


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    strategy_type: str
    version: int
    parameters_json: dict
    is_active: bool


class StrategyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    strategy_type: str = "rule_composer"
    parameters: dict = Field(default_factory=dict)


class EvaluateRequest(BaseModel):
    symbol: str
    parameters: dict | None = None  # overrides; defaults from the strategy row


class EventOut(BaseModel):
    trade_date: date
    signal_type: str
    reference_price: float | None
    execution_date: date | None
    values: dict[str, float | None]
    conditions: list[ConditionOut]


class EvaluateOut(BaseModel):
    symbol: str
    strategy_id: int
    parameters: dict
    events: list[EventOut]


class SideAnalysis(BaseModel):
    state: bool
    conditions: list[ConditionOut]


class AnalysisOut(BaseModel):
    symbol: str
    strategy_id: int
    strategy_name: str
    as_of: date
    values: dict[str, float | None]
    buy: SideAnalysis
    sell: SideAnalysis
    latest_signal: SignalOut | None


class IndicatorRecalcOut(BaseModel):
    stocks: int
    rows: int
    failed: list[SyncFailure]


class SignalScanOut(BaseModel):
    strategy_id: int
    scanned: int
    new_signals: int
    skipped: int
    failed: list[SyncFailure]
