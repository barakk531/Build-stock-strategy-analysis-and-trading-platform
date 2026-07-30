"""Rule Composer — a user-composable strategy engine.

Instead of hard-coded rules, a rule_composer strategy carries a list of
conditions the user picked from the block library (see blocks.py), combined
with ALL / ANY / at-least-k-of, for both entry (buy) and exit (sell). It
implements the same Strategy ABC as every other engine, so it works unchanged
through the scanner-free signal detector, backtests, paper accounts, and the
/strategies/{id}/evaluate preview — and its per-condition explanation renders
through the exact same Signals checklist UI.

No look-ahead: every condition is evaluated vectorized over the causal
indicator frame, and execution stays next-trading-day (inherited from the base
event machinery). Position-level risk exits (stop/trailing/take-profit) are a
separate execution-engine concern and are intentionally not part of the signal
layer here; every strategy must therefore declare at least one exit condition.
"""

from __future__ import annotations

from typing import ClassVar, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.strategies import blocks
from app.services.strategies.base import BUY, ConditionResult, Strategy


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


class ConditionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    combine: Literal["all", "any", "at_least"] = "all"
    at_least_k: int | None = None
    conditions: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> ConditionGroup:
        self.conditions = [blocks.validate_condition(c) for c in self.conditions]
        if self.combine == "at_least":
            if self.at_least_k is None or not (1 <= self.at_least_k <= len(self.conditions)):
                raise ValueError(
                    "at_least_k must be between 1 and the number of conditions"
                )
        else:
            self.at_least_k = None
        return self


class RuleComposerParams(BaseModel):
    # Universe-level fields (market-cap bounds, chart periods) may ride along on
    # the same settings blob; ignore them here, like the SMA strategy does.
    model_config = ConfigDict(extra="ignore")

    entry: ConditionGroup
    exit: ConditionGroup
    signal_mode: Literal["transition", "scan"] = "transition"
    execution_timing: Literal["next_market_open"] = "next_market_open"

    @model_validator(mode="after")
    def _non_empty(self) -> RuleComposerParams:
        if not self.entry.conditions:
            raise ValueError("entry needs at least one condition")
        if not self.exit.conditions:
            raise ValueError(
                "exit needs at least one condition "
                "(position-level risk exits are not wired yet)"
            )
        return self


class RuleComposerStrategy(Strategy):
    strategy_type: ClassVar[str] = "rule_composer"
    version: ClassVar[int] = 1
    name: ClassVar[str] = "Rule Composer"
    description: ClassVar[str] = (
        "A user-composed strategy: pick indicators and conditions from the block "
        "library, combine them with ALL / ANY / at-least-k, for entry and exit."
    )
    parameters_model: ClassVar[type[BaseModel]] = RuleComposerParams

    _GROUPS = (("e", "entry"), ("x", "exit"))

    def calculate_indicators(
        self, dataframe: pd.DataFrame, parameters: RuleComposerParams
    ) -> pd.DataFrame:
        adj = blocks.adjusted_ohlcv(dataframe)
        out = dataframe.copy()
        index = dataframe.index
        cache: dict = {}
        for prefix, attr in self._GROUPS:
            group: ConditionGroup = getattr(parameters, attr)
            for i, cond in enumerate(group.conditions):
                left = blocks.operand_series(cond["left"], adj, cache)
                right = blocks.operand_series(cond["right"], adj, cache)
                out[f"__{prefix}{i}_L"] = blocks.as_series(left, index)
                out[f"__{prefix}{i}_R"] = blocks.as_series(right, index)
                out[f"__{prefix}{i}_P"] = blocks.evaluate_condition(
                    left, right, cond["comparison"], index
                )
        return out

    def _combine(self, indicators: pd.DataFrame, prefix: str, group: ConditionGroup) -> pd.Series:
        cols = [indicators[f"__{prefix}{i}_P"] for i in range(len(group.conditions))]
        if not cols:
            return pd.Series(False, index=indicators.index)
        stacked = pd.concat(cols, axis=1).astype(bool)
        if group.combine == "all":
            return stacked.all(axis=1)
        if group.combine == "any":
            return stacked.any(axis=1)
        return stacked.sum(axis=1) >= group.at_least_k

    def compute_states(
        self, indicators: pd.DataFrame, parameters: RuleComposerParams
    ) -> tuple[pd.Series, pd.Series]:
        buy = self._combine(indicators, "e", parameters.entry)
        sell = self._combine(indicators, "x", parameters.exit)
        return buy.fillna(False), sell.fillna(False)

    def explain_row(
        self, row: pd.Series, parameters: RuleComposerParams, signal_type: str
    ) -> tuple[dict[str, float | None], list[ConditionResult]]:
        prefix, attr = ("e", "entry") if signal_type == BUY else ("x", "exit")
        group: ConditionGroup = getattr(parameters, attr)
        values: dict[str, float | None] = {}
        conditions: list[ConditionResult] = []
        for i, cond in enumerate(group.conditions):
            key = cond.get("key") or f"{prefix}{i}"
            left_v = _num(row.get(f"__{prefix}{i}_L"))
            right_v = _num(row.get(f"__{prefix}{i}_R"))
            passed = bool(row.get(f"__{prefix}{i}_P"))
            label = (
                f"{blocks.operand_label(cond['left'])} "
                f"{blocks.COMPARISONS[cond['comparison']]} "
                f"{blocks.operand_label(cond['right'])}"
            )
            values[key] = left_v
            conditions.append(
                ConditionResult(
                    key=key,
                    label=label,
                    passed=passed,
                    actual=left_v,
                    threshold=right_v,
                    comparison=cond["comparison"],
                )
            )
        return values, conditions

    def min_history(self, parameters: RuleComposerParams) -> int:
        need = 2
        for _prefix, attr in self._GROUPS:
            for cond in getattr(parameters, attr).conditions:
                need = max(need, blocks.condition_history(cond))
        return need
