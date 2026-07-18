"""SMA Trend and Volume Strategy v1 — the spec's exact rules.

Buy state on day t (ALL four true, exact values, adjusted close):
  1. SMA-long slope over the lookback >= minimum slope percent (default 0)
  2. AdjClose[t] > SMA_long[t]                    (strict)
  3. SMA_short[t] > SMA_medium[t]                 (strict)
  4. Volume[t] >= mean(Volume[t-N..t-1]) * multiplier   (prior days only)

Sell state on day t (BOTH true):
  1. AdjClose[t] < SMA_long[t]
  2. SMA_short[t] < SMA_medium[t]

Any NaN input (insufficient history, missing volume) makes the affected
condition fail — a state is never true on incomplete data.
"""

from __future__ import annotations

import math
from typing import ClassVar, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.indicators import calculator as calc
from app.services.strategies.base import BUY, ConditionResult, Strategy


class SmaTrendVolumeParams(BaseModel):
    # Accept the full strategy config from the spec; universe-level fields
    # (market-cap bounds, chart periods) are ignored here.
    model_config = ConfigDict(extra="ignore")

    sma_short_window: int = Field(20, ge=2, le=400)
    sma_medium_window: int = Field(50, ge=2, le=400)
    sma_long_window: int = Field(150, ge=2, le=400)
    sma_150_slope_lookback_days: int = Field(10, ge=1, le=200)  # trading days
    sma_150_min_slope_percent: float = Field(0.0, ge=-100, le=100)
    volume_average_days: int = Field(10, ge=1, le=250)  # trading days
    volume_multiplier: float = Field(1.0, gt=0, le=100)
    signal_mode: Literal["transition", "scan"] = "transition"
    execution_timing: Literal["next_market_open"] = "next_market_open"

    @model_validator(mode="after")
    def windows_ordered(self) -> SmaTrendVolumeParams:
        if not (self.sma_short_window < self.sma_medium_window < self.sma_long_window):
            raise ValueError("SMA windows must satisfy short < medium < long")
        return self


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _passes(actual: float | None, threshold: float | None, comparison: str) -> bool:
    if actual is None or threshold is None:
        return False
    if comparison == ">":
        return actual > threshold
    if comparison == ">=":
        return actual >= threshold
    if comparison == "<":
        return actual < threshold
    raise ValueError(f"unknown comparison {comparison}")


class SmaTrendVolumeStrategy(Strategy):
    strategy_type: ClassVar[str] = "sma_trend_volume"
    version: ClassVar[int] = 1
    name: ClassVar[str] = "SMA Trend and Volume"
    description: ClassVar[str] = (
        "Buys uptrends: flat-or-rising long SMA, price above it, short SMA above "
        "medium, on above-average volume. Sells when price and the short SMA "
        "both break down."
    )
    parameters_model: ClassVar[type[BaseModel]] = SmaTrendVolumeParams

    def calculate_indicators(
        self, dataframe: pd.DataFrame, parameters: SmaTrendVolumeParams
    ) -> pd.DataFrame:
        return calc.compute_indicators(
            dataframe,
            sma_short_window=parameters.sma_short_window,
            sma_medium_window=parameters.sma_medium_window,
            sma_long_window=parameters.sma_long_window,
            slope_lookback_days=parameters.sma_150_slope_lookback_days,
            volume_average_days=parameters.volume_average_days,
        )

    def compute_states(
        self, indicators: pd.DataFrame, parameters: SmaTrendVolumeParams
    ) -> tuple[pd.Series, pd.Series]:
        price = indicators["adjusted_close"]
        sma_s = indicators[calc.SMA_SHORT]
        sma_m = indicators[calc.SMA_MEDIUM]
        sma_l = indicators[calc.SMA_LONG]
        slope = indicators[calc.SMA_LONG_SLOPE]
        volume = indicators["volume"]
        avg_volume = indicators[calc.AVERAGE_VOLUME]

        # pandas comparisons with NaN are False, which is exactly the contract:
        # incomplete data never yields a state.
        buy = (
            (slope >= parameters.sma_150_min_slope_percent)
            & (price > sma_l)
            & (sma_s > sma_m)
            & (volume >= avg_volume * parameters.volume_multiplier)
        )
        sell = (price < sma_l) & (sma_s < sma_m)
        return buy.fillna(False), sell.fillna(False)

    def explain_row(
        self, row: pd.Series, parameters: SmaTrendVolumeParams, signal_type: str
    ) -> tuple[dict[str, float | None], list[ConditionResult]]:
        price = _num(row.get("adjusted_close"))
        sma_s = _num(row.get(calc.SMA_SHORT))
        sma_m = _num(row.get(calc.SMA_MEDIUM))
        sma_l = _num(row.get(calc.SMA_LONG))
        slope = _num(row.get(calc.SMA_LONG_SLOPE))
        volume = _num(row.get("volume"))
        avg_volume = _num(row.get(calc.AVERAGE_VOLUME))
        ratio = _num(row.get(calc.VOLUME_RATIO))

        values = {
            "adjusted_close": price,
            f"sma_{parameters.sma_short_window}": sma_s,
            f"sma_{parameters.sma_medium_window}": sma_m,
            f"sma_{parameters.sma_long_window}": sma_l,
            "sma_long_slope_percent": slope,
            "volume": volume,
            "average_volume": avg_volume,
            "volume_ratio": ratio,
        }

        long_w = parameters.sma_long_window
        lookback = parameters.sma_150_slope_lookback_days
        if signal_type == BUY:
            required_volume = (
                avg_volume * parameters.volume_multiplier if avg_volume is not None else None
            )
            conditions = [
                ConditionResult(
                    key="sma_long_slope",
                    label=f"SMA {long_w} flat or rising over {lookback} trading days",
                    passed=_passes(slope, parameters.sma_150_min_slope_percent, ">="),
                    actual=slope,
                    threshold=parameters.sma_150_min_slope_percent,
                    comparison=">=",
                ),
                ConditionResult(
                    key="price_above_sma_long",
                    label=f"Price above SMA {long_w}",
                    passed=_passes(price, sma_l, ">"),
                    actual=price,
                    threshold=sma_l,
                    comparison=">",
                ),
                ConditionResult(
                    key="sma_short_above_medium",
                    label=(
                        f"SMA {parameters.sma_short_window} above "
                        f"SMA {parameters.sma_medium_window}"
                    ),
                    passed=_passes(sma_s, sma_m, ">"),
                    actual=sma_s,
                    threshold=sma_m,
                    comparison=">",
                ),
                ConditionResult(
                    key="volume_above_average",
                    label=(
                        f"Volume at least {parameters.volume_multiplier:g}x the "
                        f"{parameters.volume_average_days}-day average"
                    ),
                    passed=_passes(volume, required_volume, ">="),
                    actual=volume,
                    threshold=required_volume,
                    comparison=">=",
                ),
            ]
        else:
            conditions = [
                ConditionResult(
                    key="price_below_sma_long",
                    label=f"Price below SMA {long_w}",
                    passed=_passes(price, sma_l, "<"),
                    actual=price,
                    threshold=sma_l,
                    comparison="<",
                ),
                ConditionResult(
                    key="sma_short_below_medium",
                    label=(
                        f"SMA {parameters.sma_short_window} below "
                        f"SMA {parameters.sma_medium_window}"
                    ),
                    passed=_passes(sma_s, sma_m, "<"),
                    actual=sma_s,
                    threshold=sma_m,
                    comparison="<",
                ),
            ]
        return values, conditions
