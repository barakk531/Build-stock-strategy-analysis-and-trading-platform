"""Strategy interface and shared signal machinery.

A concrete strategy provides indicator computation, per-day buy/sell state
Series, and a per-row explanation. This base turns states into transition
events (state flips false→true) or scan listings, always computing a day's
signal only from data available by that day's close — execution is planned for
the NEXT trading day, never the signal close.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, ClassVar

import pandas as pd
from pydantic import BaseModel

BUY = "BUY"
SELL = "SELL"


@dataclass
class ConditionResult:
    key: str
    label: str
    passed: bool
    actual: float | None
    threshold: float | None
    comparison: str  # e.g. ">", ">=", "<"


@dataclass
class SignalEvent:
    trade_date: date
    signal_type: str  # BUY | SELL
    reference_price: float | None
    # Next trading day when it exists in the data; None for the latest bar.
    execution_date: date | None
    values: dict[str, float | None] = field(default_factory=dict)
    conditions: list[ConditionResult] = field(default_factory=list)

    def conditions_payload(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "values": self.values,
            "conditions": [asdict(c) for c in self.conditions],
        }


def parameter_hash(params: BaseModel) -> str:
    canonical = json.dumps(params.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class Strategy(ABC):
    """Base class every strategy implements. Keep engine logic independent of
    Telegram, persistence, and UI concerns."""

    strategy_type: ClassVar[str]
    version: ClassVar[int]
    name: ClassVar[str]
    description: ClassVar[str] = ""
    parameters_model: ClassVar[type[BaseModel]]

    @classmethod
    def validate_parameters(cls, raw: dict | None) -> BaseModel:
        return cls.parameters_model.model_validate(raw or {})

    @abstractmethod
    def calculate_indicators(self, dataframe: pd.DataFrame, parameters: BaseModel) -> pd.DataFrame:
        """Append indicator columns (no look-ahead) to the price frame."""

    @abstractmethod
    def compute_states(
        self, indicators: pd.DataFrame, parameters: BaseModel
    ) -> tuple[pd.Series, pd.Series]:
        """Return (buy_state, sell_state) boolean Series aligned to the frame."""

    @abstractmethod
    def explain_row(
        self, row: pd.Series, parameters: BaseModel, signal_type: str
    ) -> tuple[dict[str, float | None], list[ConditionResult]]:
        """Exact values + per-condition pass/fail for one day."""

    # Spec-interface conveniences (single-row evaluation) -------------------

    def evaluate_buy_state(
        self, row: pd.Series, previous_row: pd.Series | None, parameters: BaseModel
    ) -> bool:
        _, conditions = self.explain_row(row, parameters, BUY)
        return all(c.passed for c in conditions)

    def evaluate_sell_state(
        self, row: pd.Series, previous_row: pd.Series | None, parameters: BaseModel
    ) -> bool:
        _, conditions = self.explain_row(row, parameters, SELL)
        return all(c.passed for c in conditions)

    # Shared event machinery ------------------------------------------------

    def generate_signals(
        self, dataframe: pd.DataFrame, parameters: dict | BaseModel | None
    ) -> list[SignalEvent]:
        """All signal events for the frame, honoring parameters.signal_mode:
        - transition (default): events only where state flips false→true
        - scan: an event for every day the state is true
        """
        params = (
            parameters
            if isinstance(parameters, BaseModel)
            else self.validate_parameters(parameters)
        )
        indicators = self.calculate_indicators(dataframe, params)
        buy_state, sell_state = self.compute_states(indicators, params)

        mode = getattr(params, "signal_mode", "transition")
        if mode == "transition":
            buy_events = buy_state & ~buy_state.shift(1, fill_value=False)
            sell_events = sell_state & ~sell_state.shift(1, fill_value=False)
        else:  # scan
            buy_events, sell_events = buy_state, sell_state

        next_dates = list(indicators.index[1:]) + [None]
        position = {d: i for i, d in enumerate(indicators.index)}

        events: list[SignalEvent] = []
        for signal_type, mask in ((BUY, buy_events), (SELL, sell_events)):
            for trade_date in indicators.index[mask]:
                row = indicators.loc[trade_date]
                values, conditions = self.explain_row(row, params, signal_type)
                reference = row.get("adjusted_close")
                events.append(
                    SignalEvent(
                        trade_date=trade_date,
                        signal_type=signal_type,
                        reference_price=None if pd.isna(reference) else float(reference),
                        execution_date=next_dates[position[trade_date]],
                        values=values,
                        conditions=conditions,
                    )
                )
        events.sort(key=lambda e: (e.trade_date, e.signal_type))
        return events

    def parameter_snapshot(self, parameters: dict | BaseModel | None) -> dict[str, Any]:
        params = (
            parameters
            if isinstance(parameters, BaseModel)
            else self.validate_parameters(parameters)
        )
        return params.model_dump(mode="json")
