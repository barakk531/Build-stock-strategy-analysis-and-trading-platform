"""Rule Composer engine + block library — no database needed.

Covers indicator correctness, no-look-ahead, validation rejection, and parity:
the Trend Following preset must reproduce the hard-coded SMA Trend and Volume
strategy exactly on the same data (proving the generic engine is faithful).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.services.strategies import blocks
from app.services.strategies.presets import PRESETS
from app.services.strategies.registry import get_strategy
from app.services.strategies.rule_composer import RuleComposerStrategy
from app.services.strategies.sma_trend_volume import SmaTrendVolumeStrategy


def _frame(n: int = 420, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.05, 1.2, n))
    close = np.maximum(close, 1.0)
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame(
        {
            "adjusted_close": close,
            "close": close,  # factor 1 -> adjusted OHLC == raw
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
        },
        index=idx,
    )


def _adj(frame):
    return blocks.adjusted_ohlcv(frame)


# Compact operand/condition builders for readable inline rule sets.
def _c(left, op, right):
    return {"left": left, "comparison": op, "right": right}


def _price():
    return {"type": "price"}


def _ind(name, **params):
    return {"type": "indicator", "name": name, "params": params}


def _const(v):
    return {"type": "const", "value": v}


def _group(*conditions, combine="all", at_least_k=None):
    grp = {"combine": combine, "conditions": list(conditions)}
    if at_least_k is not None:
        grp["at_least_k"] = at_least_k
    return grp


# --- Parity with the hard-coded SMA strategy -------------------------------


def test_trend_preset_matches_sma_trend_volume():
    frame = _frame()
    rule = get_strategy("rule_composer")
    sma = SmaTrendVolumeStrategy()

    trend_preset = next(p for p in PRESETS if p["name"].startswith("Trend Following"))
    rule_params = rule.validate_parameters(trend_preset["parameters"])
    sma_params = sma.validate_parameters(None)  # defaults: 20/50/150, vol x1, slope 0

    rule_events = {(e.trade_date, e.signal_type) for e in rule.generate_signals(frame, rule_params)}
    sma_events = {(e.trade_date, e.signal_type) for e in sma.generate_signals(frame, sma_params)}

    assert rule_events == sma_events
    assert rule_events  # the fixture actually produces signals


# --- No look-ahead ---------------------------------------------------------


def test_states_are_causal():
    """States for the first k bars must not change when later bars are added."""
    frame = _frame()
    rule = get_strategy("rule_composer")
    params = rule.validate_parameters(
        next(p for p in PRESETS if p["name"].startswith("Trend Following"))["parameters"]
    )

    full = rule.calculate_indicators(frame, params)
    buy_full, sell_full = rule.compute_states(full, params)

    k = 300
    partial = rule.calculate_indicators(frame.iloc[:k], params)
    buy_part, sell_part = rule.compute_states(partial, params)

    assert buy_full.iloc[:k].tolist() == buy_part.tolist()
    assert sell_full.iloc[:k].tolist() == sell_part.tolist()


def test_final_bar_has_no_execution_date():
    frame = _frame()
    rule = get_strategy("rule_composer")
    params = rule.validate_parameters(
        {
            "entry": _group(_c(_price(), ">", _const(0)), combine="any"),
            "exit": _group(_c(_price(), "<", _const(0)), combine="any"),
            "signal_mode": "scan",
        }
    )
    events = rule.generate_signals(frame, params)
    last = [e for e in events if e.trade_date == frame.index[-1]]
    assert last and all(e.execution_date is None for e in last)


# --- Indicator correctness -------------------------------------------------


def test_sma_operand_equals_rolling_mean():
    frame = _frame()
    adj = _adj(frame)
    sma = blocks.INDICATORS["sma"].compute(adj, {"period": 20})["value"]
    expected = frame["adjusted_close"].rolling(20).mean()
    pd.testing.assert_series_equal(sma, expected, check_names=False)


def test_rsi_within_bounds():
    frame = _frame()
    rsi = blocks.INDICATORS["rsi"].compute(_adj(frame), {"period": 14})["value"].dropna()
    assert not rsi.empty
    assert rsi.min() >= 0 and rsi.max() <= 100


def test_atr_is_non_negative():
    frame = _frame()
    atr = blocks.INDICATORS["atr"].compute(_adj(frame), {"period": 14})["value"].dropna()
    assert (atr >= 0).all()


def test_donchian_channel_excludes_current_bar():
    frame = _frame()
    adj = _adj(frame)
    high = blocks.INDICATORS["donchian"].compute(adj, {"period": 20})["high"]
    # Day t's channel is the max high over the prior 20 bars, not including t.
    t = 100
    expected = adj["high"].iloc[t - 20 : t].max()
    assert high.iloc[t] == pytest.approx(expected)


def test_cross_above_fires_only_on_the_crossing_bar():
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    left = pd.Series([1, 2, 3, 5, 4], index=idx, dtype=float)
    right = pd.Series([3, 3, 3, 3, 3], index=idx, dtype=float)
    result = blocks.evaluate_condition(left, right, "cross_above", idx)
    assert result.tolist() == [False, False, False, True, False]


def test_consecutive_up_counts_runs():
    idx = pd.date_range("2024-01-01", periods=6, freq="B")
    close = pd.Series([10, 11, 12, 11, 12, 13], index=idx, dtype=float)
    frame = pd.DataFrame(
        {"adjusted_close": close, "close": close, "open": close,
         "high": close, "low": close, "volume": 1.0},
        index=idx,
    )
    up = blocks.INDICATORS["consecutive_up"].compute(_adj(frame), {})["value"]
    assert up.tolist() == [0, 1, 2, 0, 1, 2]


# --- min_history + catalog -------------------------------------------------


def test_min_history_tracks_longest_window():
    rule = get_strategy("rule_composer")
    params = rule.validate_parameters(
        {
            "entry": _group(_c(_price(), ">", _ind("sma", period=200))),
            "exit": _group(_c(_ind("rsi", period=14), ">", _const(70))),
        }
    )
    assert rule.min_history(params) == 201  # 200 rows for SMA-200 + 1 causal margin


def test_catalog_has_all_groups_and_valid_params():
    cat = blocks.catalog()
    keys = {g["key"] for g in cat["groups"]}
    assert {"trend", "momentum", "volatility", "volume", "price_structure"} <= keys
    assert any(c["op"] == "cross_above" for c in cat["comparisons"])
    for group in cat["groups"]:
        for ind in group["indicators"]:
            assert ind["name"] in blocks.INDICATORS


# --- Validation rejection --------------------------------------------------


_VALID_EXIT = _group(_c(_price(), "<", _const(1)))


@pytest.mark.parametrize(
    "params",
    [
        # empty entry
        {"entry": _group(), "exit": _VALID_EXIT},
        # empty exit (risk exits not wired -> must have a signal exit)
        {"entry": _group(_c(_price(), ">", _const(1))), "exit": _group()},
        # unknown indicator
        {"entry": _group(_c(_price(), ">", _ind("nope"))), "exit": _VALID_EXIT},
        # at_least_k out of range
        {"entry": _group(_c(_price(), ">", _const(1)), combine="at_least", at_least_k=5),
         "exit": _VALID_EXIT},
        # cross with a constant on both sides (arity)
        {"entry": _group(_c(_const(1), "cross_above", _const(2))), "exit": _VALID_EXIT},
        # indicator param out of range
        {"entry": _group(_c(_ind("sma", period=1), ">", _const(1))), "exit": _VALID_EXIT},
    ],
)
def test_invalid_rule_sets_are_rejected(params):
    with pytest.raises(ValidationError):
        RuleComposerStrategy.validate_parameters(params)
