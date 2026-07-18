"""SmaTrendVolumeStrategy: every §19 condition, state, transition, and edge case."""

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.services.indicators import calculator as calc
from app.services.strategies.base import BUY, SELL, parameter_hash
from app.services.strategies.registry import get_strategy
from app.services.strategies.sma_trend_volume import (
    SmaTrendVolumeParams,
    SmaTrendVolumeStrategy,
)

STRATEGY = SmaTrendVolumeStrategy()


def _row(
    price=110.0, sma_s=105.0, sma_m=100.0, sma_l=95.0,
    slope=0.5, volume=200.0, avg_volume=100.0,
):
    return pd.Series(
        {
            "adjusted_close": price,
            calc.SMA_SHORT: sma_s,
            calc.SMA_MEDIUM: sma_m,
            calc.SMA_LONG: sma_l,
            calc.SMA_LONG_SLOPE: slope,
            "volume": volume,
            calc.AVERAGE_VOLUME: avg_volume,
            calc.VOLUME_RATIO: volume / avg_volume if avg_volume else np.nan,
        }
    )


def _params(**overrides):
    return SmaTrendVolumeParams(**overrides)


def _buy_conditions(row, params=None):
    _, conditions = STRATEGY.explain_row(row, params or _params(), BUY)
    return {c.key: c.passed for c in conditions}


def _sell_conditions(row, params=None):
    _, conditions = STRATEGY.explain_row(row, params or _params(), SELL)
    return {c.key: c.passed for c in conditions}


# ---------------- parameter validation ----------------


def test_default_parameters_match_spec():
    p = _params()
    assert (p.sma_short_window, p.sma_medium_window, p.sma_long_window) == (20, 50, 150)
    assert p.sma_150_slope_lookback_days == 10
    assert p.sma_150_min_slope_percent == 0
    assert p.volume_average_days == 10
    assert p.volume_multiplier == 1.0
    assert p.signal_mode == "transition"
    assert p.execution_timing == "next_market_open"


def test_parameter_validation_rejects_bad_window_order():
    with pytest.raises(ValidationError):
        _params(sma_short_window=50, sma_medium_window=20)


def test_parameter_validation_rejects_nonpositive_multiplier():
    with pytest.raises(ValidationError):
        _params(volume_multiplier=0)


def test_full_spec_config_accepted_with_extra_universe_keys():
    p = SmaTrendVolumeStrategy.validate_parameters(
        {
            "sma_short_window": 20, "sma_medium_window": 50, "sma_long_window": 150,
            "minimum_market_cap": None, "maximum_market_cap": None,
            "history_period_years": 20, "chart_period_years": 5,
            "signal_mode": "transition", "execution_timing": "next_market_open",
        }
    )
    assert p.sma_long_window == 150


def test_parameter_hash_stable_and_order_independent():
    validate = SmaTrendVolumeStrategy.validate_parameters
    a = validate({"volume_multiplier": 1.2, "volume_average_days": 20})
    b = validate({"volume_average_days": 20, "volume_multiplier": 1.2})
    assert parameter_hash(a) == parameter_hash(b)
    c = SmaTrendVolumeStrategy.validate_parameters({"volume_multiplier": 1.5})
    assert parameter_hash(a) != parameter_hash(c)


# ---------------- buy conditions individually ----------------


def test_buy_all_conditions_pass():
    assert all(_buy_conditions(_row()).values())


def test_buy_condition1_slope_below_minimum_fails():
    passed = _buy_conditions(_row(slope=-0.01))
    assert passed["sma_long_slope"] is False
    assert passed["price_above_sma_long"] is True  # others unaffected


def test_buy_condition1_flat_slope_passes_with_zero_minimum():
    assert _buy_conditions(_row(slope=0.0))["sma_long_slope"] is True


def test_buy_condition1_respects_custom_minimum():
    params = _params(sma_150_min_slope_percent=1.0)
    assert _buy_conditions(_row(slope=0.5), params)["sma_long_slope"] is False
    assert _buy_conditions(_row(slope=1.0), params)["sma_long_slope"] is True


def test_buy_condition2_price_equal_sma_long_fails_strict():
    assert _buy_conditions(_row(price=95.0, sma_l=95.0))["price_above_sma_long"] is False


def test_buy_condition3_sma_short_equal_medium_fails_strict():
    assert _buy_conditions(_row(sma_s=100.0, sma_m=100.0))["sma_short_above_medium"] is False


def test_buy_condition4_volume_exactly_at_threshold_passes():
    params = _params(volume_multiplier=1.5)
    at_threshold = _buy_conditions(_row(volume=150.0, avg_volume=100.0), params)
    below = _buy_conditions(_row(volume=149.99, avg_volume=100.0), params)
    assert at_threshold["volume_above_average"] is True
    assert below["volume_above_average"] is False


def test_buy_condition4_missing_volume_fails():
    assert _buy_conditions(_row(volume=np.nan))["volume_above_average"] is False


def test_buy_condition4_zero_volume_fails_against_positive_average():
    assert _buy_conditions(_row(volume=0.0))["volume_above_average"] is False


def test_buy_insufficient_history_nan_smas_fail():
    passed = _buy_conditions(_row(sma_l=np.nan, slope=np.nan))
    assert passed["sma_long_slope"] is False
    assert passed["price_above_sma_long"] is False


# ---------------- sell conditions ----------------


def test_sell_both_conditions():
    passed = _sell_conditions(_row(price=90.0, sma_s=95.0, sma_m=100.0, sma_l=95.0))
    assert passed == {"price_below_sma_long": True, "sma_short_below_medium": True}


def test_sell_price_equal_sma_long_fails_strict():
    assert _sell_conditions(_row(price=95.0, sma_l=95.0))["price_below_sma_long"] is False


def test_sell_sma_equal_fails_strict():
    assert _sell_conditions(_row(sma_s=100.0, sma_m=100.0))["sma_short_below_medium"] is False


# ---------------- states & transitions (synthetic frame) ----------------


def _state_frame(buy_days: list[bool], sell_days: list[bool] | None = None) -> pd.DataFrame:
    """Frame whose engineered indicator columns produce the requested states."""
    n = len(buy_days)
    sell_days = sell_days or [False] * n
    rows = []
    for is_buy, is_sell in zip(buy_days, sell_days, strict=True):
        if is_buy:
            rows.append(dict(adjusted_close=110, sma=105, sma_m=100, sma_l=95,
                             slope=0.5, volume=200, avg=100))
        elif is_sell:
            rows.append(dict(adjusted_close=90, sma=95, sma_m=100, sma_l=95,
                             slope=-1.0, volume=50, avg=100))
        else:
            rows.append(dict(adjusted_close=96, sma=99, sma_m=100, sma_l=95,
                             slope=0.5, volume=50, avg=100))
    index = [d.date() for d in pd.bdate_range("2026-03-02", periods=n)]
    return pd.DataFrame(
        {
            "adjusted_close": [r["adjusted_close"] for r in rows],
            calc.SMA_SHORT: [r["sma"] for r in rows],
            calc.SMA_MEDIUM: [r["sma_m"] for r in rows],
            calc.SMA_LONG: [r["sma_l"] for r in rows],
            calc.SMA_LONG_SLOPE: [r["slope"] for r in rows],
            "volume": [r["volume"] for r in rows],
            calc.AVERAGE_VOLUME: [r["avg"] for r in rows],
            calc.VOLUME_RATIO: [r["volume"] / r["avg"] for r in rows],
        },
        index=index,
    )


class _PrecomputedStrategy(SmaTrendVolumeStrategy):
    """Skip indicator recomputation — the frame already carries indicators."""

    def calculate_indicators(self, dataframe, parameters):
        return dataframe


def test_buy_transition_fires_once_per_streak():
    frame = _state_frame([False, True, True, True, False, True])
    events = _PrecomputedStrategy().generate_signals(frame, {"signal_mode": "transition"})
    buys = [e for e in events if e.signal_type == BUY]
    assert [str(e.trade_date) for e in buys] == ["2026-03-03", "2026-03-09"]


def test_scan_mode_lists_every_active_day():
    frame = _state_frame([False, True, True, True, False, True])
    events = _PrecomputedStrategy().generate_signals(frame, {"signal_mode": "scan"})
    assert len([e for e in events if e.signal_type == BUY]) == 4


def test_sell_transition_and_execution_next_trading_day():
    frame = _state_frame([False, False, False], [False, True, False])
    events = _PrecomputedStrategy().generate_signals(frame, {})
    assert len(events) == 1
    event = events[0]
    assert event.signal_type == SELL
    assert str(event.trade_date) == "2026-03-03"
    assert str(event.execution_date) == "2026-03-04"  # next trading day, never same close
    assert event.reference_price == 90.0


def test_latest_bar_has_no_execution_date_yet():
    frame = _state_frame([False, True])
    events = _PrecomputedStrategy().generate_signals(frame, {})
    assert events[0].execution_date is None


def test_buy_and_sell_states_are_mutually_exclusive():
    rng = np.random.default_rng(11)
    prices = 100 + rng.normal(0, 2, 400).cumsum()
    volumes = rng.integers(100, 300, 400).astype(float)
    index = [d.date() for d in pd.bdate_range("2024-01-01", periods=400)]
    frame = pd.DataFrame({"adjusted_close": prices, "volume": volumes}, index=index)
    params = STRATEGY.validate_parameters({})
    indicators = STRATEGY.calculate_indicators(frame, params)
    buy, sell = STRATEGY.compute_states(indicators, params)
    assert not (buy & sell).any()


def test_signal_includes_full_condition_explanation():
    frame = _state_frame([False, True])
    event = _PrecomputedStrategy().generate_signals(frame, {})[0]
    payload = event.conditions_payload()
    assert payload["signal_type"] == BUY
    assert {c["key"] for c in payload["conditions"]} == {
        "sma_long_slope", "price_above_sma_long", "sma_short_above_medium", "volume_above_average",
    }
    assert all(c["passed"] for c in payload["conditions"])
    assert payload["values"]["adjusted_close"] == 110.0
    assert payload["values"]["volume_ratio"] == 2.0


# ---------------- end-to-end with real rolling windows ----------------


def _trend_frame() -> pd.DataFrame:
    """Rising price series with a volume pop near the end (small windows)."""
    prices = list(np.linspace(100, 120, 30))
    volumes = [100.0] * 28 + [400.0, 400.0]
    index = [d.date() for d in pd.bdate_range("2026-01-01", periods=30)]
    return pd.DataFrame({"adjusted_close": prices, "volume": volumes}, index=index)


_SMALL = {
    "sma_short_window": 3, "sma_medium_window": 5, "sma_long_window": 10,
    "sma_150_slope_lookback_days": 3, "volume_average_days": 5,
    # >1 so steady volume (== its own average) can't satisfy the condition;
    # only the engineered end-of-series volume pop passes.
    "volume_multiplier": 1.2,
}


def test_end_to_end_buy_signal_on_trend_with_volume():
    events = STRATEGY.generate_signals(_trend_frame(), _SMALL)
    buys = [e for e in events if e.signal_type == BUY]
    assert len(buys) == 1
    assert str(buys[0].trade_date) == "2026-02-10"  # the first volume-pop day


def test_fewer_rows_than_long_window_produces_no_signals():
    frame = _trend_frame().iloc[:8]  # < long window of 10
    assert STRATEGY.generate_signals(frame, _SMALL) == []


def test_signals_are_reproducible():
    frame = _trend_frame()
    first = STRATEGY.generate_signals(frame, _SMALL)
    second = STRATEGY.generate_signals(frame, _SMALL)
    assert [(e.trade_date, e.signal_type, e.reference_price) for e in first] == [
        (e.trade_date, e.signal_type, e.reference_price) for e in second
    ]


def test_registry_returns_engine():
    engine = get_strategy("sma_trend_volume")
    assert isinstance(engine, SmaTrendVolumeStrategy)
    with pytest.raises(ValueError):
        get_strategy("nope")
