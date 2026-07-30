"""Indicator/operand library for the composable rule engine (rule_composer).

Every indicator is vectorized and causal (no look-ahead): a value on day `t`
uses only bars up to and including `t`, except channel/average operands that
deliberately exclude the current bar (Donchian channel, volume average) so a
"breakout above the prior N-day high" is a real breakout. OHLC is put on the
**adjusted** basis (raw high/low/open scaled by adjusted_close / close) so
splits and dividends never create false signals, matching the rest of the
platform.

An *operand* is one side of a condition:
  {"type": "price"}                              -> adjusted close
  {"type": "const", "value": 30}                 -> a constant
  {"type": "indicator", "name": "rsi",
   "params": {"period": 14}, "field": "value"}   -> an indicator series

The registry is also the source of truth for the /strategy-blocks catalog the
builder UI consumes, so blocks are defined once here, never duplicated in JS.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# --- Comparisons -----------------------------------------------------------

COMPARISONS: dict[str, str] = {
    ">": "above",
    ">=": "at least",
    "<": "below",
    "<=": "at most",
    "cross_above": "crosses above",
    "cross_below": "crosses below",
}
_CROSS = {"cross_above", "cross_below"}


# --- Adjusted OHLCV --------------------------------------------------------


def adjusted_ohlcv(frame: pd.DataFrame) -> dict[str, pd.Series]:
    """Split/dividend-adjusted O/H/L/C plus raw volume, aligned to the frame.

    Raw high/low/open are scaled by adjusted_close / close so every price
    operand shares one basis; volume stays raw (matches the existing
    volume_ratio semantics)."""
    close = frame["adjusted_close"].astype(float)
    raw_close = frame["close"].astype(float)
    factor = (close / raw_close).where(raw_close > 0)
    high = frame["high"].astype(float) * factor if "high" in frame else close
    low = frame["low"].astype(float) * factor if "low" in frame else close
    open_ = frame["open"].astype(float) * factor if "open" in frame else close
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": frame["volume"].astype(float),
    }


def _clean(series: pd.Series) -> pd.Series:
    return series.replace([np.inf, -np.inf], np.nan)


def _wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (RMA) via EWM, NaN until `period` observations."""
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


# --- Indicator implementations --------------------------------------------
# Each returns dict[field -> Series]; single-output indicators use "value".


def _sma(a, p):
    n = p["period"]
    return {"value": a["close"].rolling(n, min_periods=n).mean()}


def _ema(a, p):
    n = p["period"]
    return {"value": a["close"].ewm(span=n, adjust=False, min_periods=n).mean()}


def _rsi(a, p):
    n = p["period"]
    delta = a["close"].diff()
    gain = _wilder(delta.clip(lower=0), n)
    loss = _wilder(-delta.clip(upper=0), n)
    rs = gain / loss
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.where(loss != 0, 100.0)  # all-gains window -> RSI 100
    return {"value": _clean(rsi)}


def _macd(a, p):
    fast = a["close"].ewm(span=p["fast"], adjust=False, min_periods=p["fast"]).mean()
    slow = a["close"].ewm(span=p["slow"], adjust=False, min_periods=p["slow"]).mean()
    line = fast - slow
    signal = line.ewm(span=p["signal"], adjust=False, min_periods=p["signal"]).mean()
    return {"line": line, "signal": signal, "hist": line - signal}


def _true_range(a) -> pd.Series:
    prev_close = a["close"].shift(1)
    return pd.concat(
        [a["high"] - a["low"], (a["high"] - prev_close).abs(), (a["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def _atr(a, p):
    return {"value": _wilder(_true_range(a), p["period"])}


def _adx(a, p):
    n = p["period"]
    up = a["high"].diff()
    down = -a["low"].diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr = _wilder(_true_range(a), n)
    plus_di = 100.0 * _wilder(plus_dm, n) / atr
    minus_di = 100.0 * _wilder(minus_dm, n) / atr
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return {"value": _clean(_wilder(_clean(dx), n))}


def _stochastic(a, p):
    k_n, d_n = p["k_period"], p["d_period"]
    low_n = a["low"].rolling(k_n, min_periods=k_n).min()
    high_n = a["high"].rolling(k_n, min_periods=k_n).max()
    k = 100.0 * (a["close"] - low_n) / (high_n - low_n)
    k = _clean(k)
    return {"k": k, "d": k.rolling(d_n, min_periods=d_n).mean()}


def _williams_r(a, p):
    n = p["period"]
    high_n = a["high"].rolling(n, min_periods=n).max()
    low_n = a["low"].rolling(n, min_periods=n).min()
    return {"value": _clean(-100.0 * (high_n - a["close"]) / (high_n - low_n))}


def _roc(a, p):
    n = p["period"]
    return {"value": (a["close"] / a["close"].shift(n) - 1.0) * 100.0}


def _bollinger(a, p):
    n, k = p["period"], p["k"]
    mid = a["close"].rolling(n, min_periods=n).mean()
    std = a["close"].rolling(n, min_periods=n).std(ddof=0)
    return {"upper": mid + k * std, "mid": mid, "lower": mid - k * std}


def _hist_vol(a, p):
    n = p["period"]
    logret = np.log(a["close"] / a["close"].shift(1))
    return {"value": logret.rolling(n, min_periods=n).std(ddof=1) * math.sqrt(252) * 100.0}


def _ma_slope(a, p):
    n, look = p["period"], p["lookback"]
    sma = a["close"].rolling(n, min_periods=n).mean()
    return {"value": (sma / sma.shift(look) - 1.0) * 100.0}


def _donchian(a, p):
    n = p["period"]
    # Prior N bars only (shift 1) so a close above `high` is a genuine breakout.
    return {
        "high": a["high"].rolling(n, min_periods=n).max().shift(1),
        "low": a["low"].rolling(n, min_periods=n).min().shift(1),
    }


def _pct_from_high(a, p):
    n = p["window"]
    roll_max = a["close"].rolling(n, min_periods=n).max()
    return {"value": (a["close"] / roll_max - 1.0) * 100.0}


def _pct_from_low(a, p):
    n = p["window"]
    roll_min = a["close"].rolling(n, min_periods=n).min()
    return {"value": (a["close"] / roll_min - 1.0) * 100.0}


def _gap_percent(a, _p):
    return {"value": (a["open"] / a["close"].shift(1) - 1.0) * 100.0}


def _consecutive(up: bool) -> Callable:
    def compute(a, _p):
        moved = a["close"].diff() > 0 if up else a["close"].diff() < 0
        # Count of consecutive True ending at each bar (resets on False).
        resets = (~moved).cumsum()
        return {"value": moved.groupby(resets).cumsum().astype(float)}

    return compute


def _volume(a, _p):
    return {"value": a["volume"]}


def _avg_volume(a, p):
    n = p["period"]
    return {"value": a["volume"].shift(1).rolling(n, min_periods=n).mean()}


def _volume_ratio(a, p):
    n = p["period"]
    avg = a["volume"].shift(1).rolling(n, min_periods=n).mean()
    return {"value": _clean(a["volume"] / avg)}


def _obv(a, _p):
    direction = np.sign(a["close"].diff()).fillna(0.0)
    return {"value": (direction * a["volume"]).cumsum()}


def _dollar_volume(a, _p):
    return {"value": a["close"] * a["volume"]}


# --- Registry --------------------------------------------------------------


@dataclass(frozen=True)
class Param:
    name: str
    default: float
    minimum: float
    maximum: float
    integer: bool = True


@dataclass(frozen=True)
class Indicator:
    name: str
    group: str
    label_template: str  # e.g. "SMA {period}"
    fields: tuple[str, ...]
    params: tuple[Param, ...]
    compute: Callable[[dict, dict], dict]
    history: Callable[[dict], int]
    default_field: str = "value"
    field_labels: dict[str, str] = field(default_factory=dict)

    def label(self, params: dict, fld: str) -> str:
        base = self.label_template.format(**params)
        suffix = self.field_labels.get(fld, "" if fld == "value" else fld)
        return f"{base} {suffix}".strip()


def _p(name, default, lo, hi, integer=True) -> Param:
    return Param(name, default, lo, hi, integer)


INDICATORS: dict[str, Indicator] = {}


def _register(ind: Indicator) -> None:
    INDICATORS[ind.name] = ind


_register(Indicator("sma", "trend", "SMA {period}", ("value",), (_p("period", 20, 2, 400),),
                     _sma, lambda p: p["period"]))
_register(Indicator("ema", "trend", "EMA {period}", ("value",), (_p("period", 20, 2, 400),),
                     _ema, lambda p: p["period"]))
_register(Indicator("ma_slope", "trend", "SMA {period} slope", ("value",),
                     (_p("period", 150, 2, 400), _p("lookback", 10, 1, 200)),
                     _ma_slope, lambda p: p["period"] + p["lookback"]))
_register(Indicator("macd", "trend", "MACD({fast}/{slow}/{signal})",
                     ("line", "signal", "hist"),
                     (_p("fast", 12, 2, 200), _p("slow", 26, 3, 400), _p("signal", 9, 1, 200)),
                     _macd, lambda p: p["slow"] + p["signal"], default_field="line",
                     field_labels={"line": "line", "signal": "signal", "hist": "histogram"}))
_register(Indicator("adx", "trend", "ADX {period}", ("value",), (_p("period", 14, 2, 200),),
                     _adx, lambda p: 3 * p["period"]))
_register(Indicator("donchian", "trend", "Donchian {period}", ("high", "low"),
                     (_p("period", 20, 2, 400),), _donchian, lambda p: p["period"] + 1,
                     default_field="high",
                     field_labels={"high": "high", "low": "low"}))

_register(Indicator("rsi", "momentum", "RSI {period}", ("value",), (_p("period", 14, 2, 200),),
                     _rsi, lambda p: p["period"] + 1))
_register(Indicator("stochastic", "momentum", "Stochastic({k_period}/{d_period})", ("k", "d"),
                     (_p("k_period", 14, 1, 200), _p("d_period", 3, 1, 100)),
                     _stochastic, lambda p: p["k_period"] + p["d_period"], default_field="k",
                     field_labels={"k": "%K", "d": "%D"}))
_register(Indicator("roc", "momentum", "ROC {period}", ("value",), (_p("period", 12, 1, 400),),
                     _roc, lambda p: p["period"] + 1))
_register(Indicator("return_n", "momentum", "{period}-day return", ("value",),
                     (_p("period", 21, 1, 400),), _roc, lambda p: p["period"] + 1))
_register(Indicator("williams_r", "momentum", "Williams %R {period}", ("value",),
                     (_p("period", 14, 2, 200),), _williams_r, lambda p: p["period"]))

_register(Indicator("bollinger", "volatility", "Bollinger({period},{k})",
                     ("upper", "mid", "lower"),
                     (_p("period", 20, 2, 400), _p("k", 2.0, 0.1, 5.0, integer=False)),
                     _bollinger, lambda p: p["period"], default_field="upper",
                     field_labels={"upper": "upper", "mid": "middle", "lower": "lower"}))
_register(Indicator("atr", "volatility", "ATR {period}", ("value",), (_p("period", 14, 2, 200),),
                     _atr, lambda p: p["period"] + 1))
_register(Indicator("hist_vol", "volatility", "Volatility {period}", ("value",),
                     (_p("period", 20, 2, 400),), _hist_vol, lambda p: p["period"] + 1))

_register(Indicator("volume", "volume", "Volume", ("value",), (), _volume, lambda p: 1))
_register(Indicator("avg_volume", "volume", "Avg volume {period}", ("value",),
                     (_p("period", 20, 1, 250),), _avg_volume, lambda p: p["period"] + 1))
_register(Indicator("volume_ratio", "volume", "Volume ratio {period}", ("value",),
                     (_p("period", 20, 1, 250),), _volume_ratio, lambda p: p["period"] + 1))
_register(Indicator("obv", "volume", "OBV", ("value",), (), _obv, lambda p: 2))
_register(Indicator("dollar_volume", "volume", "Dollar volume", ("value",), (), _dollar_volume,
                     lambda p: 1))

_register(Indicator("pct_from_52w_high", "price_structure", "% from {window}-bar high", ("value",),
                     (_p("window", 252, 20, 504),), _pct_from_high, lambda p: p["window"]))
_register(Indicator("pct_from_52w_low", "price_structure", "% from {window}-bar low", ("value",),
                     (_p("window", 252, 20, 504),), _pct_from_low, lambda p: p["window"]))
_register(Indicator("gap_percent", "price_structure", "Gap %", ("value",), (), _gap_percent,
                     lambda p: 2))
_register(Indicator("consecutive_up", "price_structure", "Consecutive up days", ("value",), (),
                     _consecutive(up=True), lambda p: 2))
_register(Indicator("consecutive_down", "price_structure", "Consecutive down days", ("value",), (),
                     _consecutive(up=False), lambda p: 2))


GROUP_LABELS = {
    "trend": "Trend",
    "momentum": "Momentum",
    "volatility": "Volatility",
    "volume": "Volume",
    "price_structure": "Price structure",
}


# --- Operand + condition validation and evaluation -------------------------


class BlockError(ValueError):
    """A malformed operand, indicator, or comparison."""


def normalize_params(indicator: Indicator, raw: dict | None) -> dict:
    """Fill defaults, reject unknown keys, range-check, and coerce ints."""
    raw = dict(raw or {})
    allowed = {p.name for p in indicator.params}
    unknown = set(raw) - allowed
    if unknown:
        raise BlockError(f"{indicator.name}: unknown params {sorted(unknown)}")
    out: dict[str, Any] = {}
    for spec in indicator.params:
        value = raw.get(spec.name, spec.default)
        try:
            value = int(value) if spec.integer else float(value)
        except (TypeError, ValueError) as exc:
            raise BlockError(f"{indicator.name}.{spec.name}: not a number") from exc
        if not (spec.minimum <= value <= spec.maximum):
            raise BlockError(
                f"{indicator.name}.{spec.name}={value} out of range "
                f"[{spec.minimum}, {spec.maximum}]"
            )
        out[spec.name] = value
    return out


def validate_operand(operand: Any) -> dict:
    """Validate one operand and return a normalized copy."""
    if not isinstance(operand, dict) or "type" not in operand:
        raise BlockError("operand must be an object with a 'type'")
    kind = operand["type"]
    if kind == "price":
        return {"type": "price"}
    if kind == "const":
        try:
            return {"type": "const", "value": float(operand["value"])}
        except (KeyError, TypeError, ValueError) as exc:
            raise BlockError("const operand needs a numeric 'value'") from exc
    if kind == "indicator":
        name = operand.get("name")
        indicator = INDICATORS.get(name)
        if indicator is None:
            raise BlockError(f"unknown indicator {name!r}")
        params = normalize_params(indicator, operand.get("params"))
        fld = operand.get("field") or indicator.default_field
        if fld not in indicator.fields:
            raise BlockError(f"{name}: unknown field {fld!r}; choose {list(indicator.fields)}")
        return {"type": "indicator", "name": name, "params": params, "field": fld}
    raise BlockError(f"unknown operand type {kind!r}")


def is_series_operand(operand: dict) -> bool:
    return operand["type"] != "const"


def operand_label(operand: dict) -> str:
    if operand["type"] == "price":
        return "Price"
    if operand["type"] == "const":
        return f"{operand['value']:g}"
    indicator = INDICATORS[operand["name"]]
    return indicator.label(operand["params"], operand["field"])


def operand_series(operand: dict, adj: dict, cache: dict) -> pd.Series | float:
    """Resolve an operand to a Series (or scalar for const), computing and
    caching indicators as needed."""
    if operand["type"] == "const":
        return operand["value"]
    if operand["type"] == "price":
        return adj["close"]
    key = (operand["name"], tuple(sorted(operand["params"].items())))
    if key not in cache:
        cache[key] = INDICATORS[operand["name"]].compute(adj, operand["params"])
    return cache[key][operand["field"]]


def as_series(value, index) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    return pd.Series(value, index=index, dtype=float)


def evaluate_condition(left, right, comparison: str, index) -> pd.Series:
    """Boolean Series for one condition; NaN comparisons are False."""
    left_s = as_series(left, index)
    right_s = as_series(right, index)
    if comparison == ">":
        result = left_s > right_s
    elif comparison == ">=":
        result = left_s >= right_s
    elif comparison == "<":
        result = left_s < right_s
    elif comparison == "<=":
        result = left_s <= right_s
    elif comparison == "cross_above":
        result = (left_s > right_s) & (left_s.shift(1) <= right_s.shift(1))
    elif comparison == "cross_below":
        result = (left_s < right_s) & (left_s.shift(1) >= right_s.shift(1))
    else:
        raise BlockError(f"unknown comparison {comparison!r}")
    return result.fillna(False)


def validate_condition(condition: Any) -> dict:
    """Validate {left, comparison, right, key?} and return a normalized copy."""
    if not isinstance(condition, dict):
        raise BlockError("condition must be an object")
    comparison = condition.get("comparison")
    if comparison not in COMPARISONS:
        raise BlockError(f"unknown comparison {comparison!r}; choose {list(COMPARISONS)}")
    left = validate_operand(condition.get("left"))
    right = validate_operand(condition.get("right"))
    if comparison in _CROSS and not (is_series_operand(left) and is_series_operand(right)):
        raise BlockError(f"{comparison} needs two series operands, not a constant on both sides")
    out = {"left": left, "comparison": comparison, "right": right}
    if condition.get("key"):
        out["key"] = str(condition["key"])
    return out


def condition_history(condition: dict) -> int:
    need = 2
    for side in ("left", "right"):
        operand = condition[side]
        if operand["type"] == "indicator":
            need = max(need, INDICATORS[operand["name"]].history(operand["params"]) + 1)
    return need


def catalog() -> dict:
    """Data-driven block catalog for the builder UI (/strategy-blocks)."""
    groups: dict[str, list] = {}
    for ind in INDICATORS.values():
        groups.setdefault(ind.group, []).append(
            {
                "name": ind.name,
                "label": ind.label_template,
                "fields": list(ind.fields),
                "default_field": ind.default_field,
                "params": [
                    {
                        "name": p.name,
                        "default": p.default,
                        "min": p.minimum,
                        "max": p.maximum,
                        "integer": p.integer,
                    }
                    for p in ind.params
                ],
            }
        )
    return {
        "groups": [
            {"key": key, "label": GROUP_LABELS.get(key, key), "indicators": groups[key]}
            for key in GROUP_LABELS
            if key in groups
        ],
        "comparisons": [{"op": op, "label": label} for op, label in COMPARISONS.items()],
        "operand_types": ["price", "indicator", "const"],
    }
