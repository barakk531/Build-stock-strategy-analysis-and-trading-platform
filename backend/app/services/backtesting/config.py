"""Backtest configuration — every spec §15 input, validated up front."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Yahoo-style tickers: letters/digits with ., -, ^ (indices), = (futures).
SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,20}$")


class BacktestConfig(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # None -> the seeded default strategy.
    strategy_id: int | None = None
    # Strategy parameter overrides; empty -> the strategy row's stored params.
    parameters: dict = Field(default_factory=dict)

    start_date: date
    end_date: date
    initial_cash: float = Field(100_000.0, gt=0, le=1e12)

    # Universe filters (survivorship bias: current constituents, disclosed).
    symbols: list[str] | None = None
    sectors: list[str] | None = None
    min_market_cap: int | None = Field(None, ge=0)
    max_market_cap: int | None = Field(None, ge=0)

    # Portfolio rules (spec §13 defaults).
    max_open_positions: int = Field(10, ge=1, le=200)
    position_sizing_type: Literal["equal_weight"] = "equal_weight"
    position_size_percent: float = Field(10.0, gt=0, le=100)
    allow_fractional_shares: bool = False

    # Costs.
    commission_per_trade: float = Field(0.0, ge=0, le=1000)
    slippage_percent: float = Field(0.05, ge=0, le=10)

    execution_timing: Literal["next_market_open"] = "next_market_open"
    benchmark_symbol: str | None = "^GSPC"

    @model_validator(mode="after")
    def dates_ordered(self) -> BacktestConfig:
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if (
            self.min_market_cap is not None
            and self.max_market_cap is not None
            and self.min_market_cap > self.max_market_cap
        ):
            raise ValueError("min_market_cap must not exceed max_market_cap")
        if self.symbols is not None:
            self.symbols = [s.strip().upper() for s in self.symbols if s.strip()] or None
            if self.symbols:
                bad = [s for s in self.symbols if not SYMBOL_RE.match(s)]
                if bad:
                    raise ValueError(f"invalid symbols: {bad[:5]}")
        if self.benchmark_symbol is not None:
            self.benchmark_symbol = self.benchmark_symbol.strip().upper() or None
            if self.benchmark_symbol and not SYMBOL_RE.match(self.benchmark_symbol):
                raise ValueError(f"invalid benchmark symbol: {self.benchmark_symbol!r}")
        return self

    def settings_snapshot(self) -> dict:
        """Account-level settings persisted on the run row."""
        return {
            "max_open_positions": self.max_open_positions,
            "position_sizing_type": self.position_sizing_type,
            "position_size_percent": self.position_size_percent,
            "allow_fractional_shares": self.allow_fractional_shares,
            "execution_timing": self.execution_timing,
            "benchmark_symbol": self.benchmark_symbol,
        }
