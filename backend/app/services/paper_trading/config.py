"""Paper-account settings — spec §13 defaults, validated at creation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AccountSettings(BaseModel):
    position_sizing_type: Literal["equal_weight"] = "equal_weight"
    maximum_open_positions: int = Field(10, ge=1, le=200)
    position_size_percent: float = Field(10.0, gt=0, le=100)
    commission_per_trade: float = Field(0.0, ge=0, le=1000)
    slippage_percent: float = Field(0.05, ge=0, le=10)
    allow_fractional_shares: bool = False
    allow_short_selling: Literal[False] = False  # v1: long only
    allow_leverage: Literal[False] = False  # v1: cash account
    execution_timing: Literal["next_market_open"] = "next_market_open"
    minimum_market_cap: int | None = Field(None, ge=0)
    maximum_market_cap: int | None = Field(None, ge=0)
    benchmark_symbol: str | None = "^GSPC"

    @model_validator(mode="after")
    def caps_ordered(self) -> AccountSettings:
        if (
            self.minimum_market_cap is not None
            and self.maximum_market_cap is not None
            and self.minimum_market_cap > self.maximum_market_cap
        ):
            raise ValueError("minimum_market_cap must not exceed maximum_market_cap")
        if self.benchmark_symbol is not None:
            self.benchmark_symbol = self.benchmark_symbol.strip().upper() or None
            if self.benchmark_symbol is not None:
                from app.services.backtesting.config import SYMBOL_RE

                if not SYMBOL_RE.match(self.benchmark_symbol):
                    raise ValueError(
                        f"invalid benchmark symbol: {self.benchmark_symbol!r}"
                    )
        return self
