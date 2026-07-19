from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.paper_trading.config import AccountSettings


class AccountCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    strategy_id: int | None = None  # None -> seeded default strategy
    parameters: dict = Field(default_factory=dict)  # empty -> strategy defaults
    initial_cash: float = Field(100_000.0, gt=0, le=1e12)
    start_date: date
    settings: AccountSettings = Field(default_factory=AccountSettings)


class AccountUpdateIn(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    # Settings may only change while the account has no orders yet.
    settings: AccountSettings | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    strategy_id: int
    initial_cash: float
    cash_balance: float
    base_currency: str
    start_date: date
    status: str
    created_at: datetime
    # Enriched from the latest snapshot / relations:
    total_equity: float | None = None
    total_return_pct: float | None = None
    open_positions: int | None = None
    pending_orders: int | None = None
    last_snapshot_date: date | None = None


class AccountDetailOut(AccountOut):
    strategy_parameter_snapshot_json: dict
    parameter_hash: str
    settings_json: dict


class AccountListOut(BaseModel):
    items: list[AccountOut]
    total: int


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    quantity: float
    average_entry_price: float
    cost_basis: float
    opened_at: date
    closed_at: date | None
    status: str
    realized_pnl: float | None
    # OPEN positions only:
    last_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None


class PositionListOut(BaseModel):
    items: list[PositionOut]
    total: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    side: str
    quantity: float | None
    signal_date: date
    scheduled_execution_date: date | None
    executed_at: date | None
    execution_price: float | None
    commission: float | None
    slippage: float | None
    status: str
    rejection_reason: str | None
    created_at: datetime


class OrderListOut(BaseModel):
    items: list[OrderOut]
    total: int
    limit: int
    offset: int


class ProcessOut(BaseModel):
    accounts: int
    results: list[dict]
