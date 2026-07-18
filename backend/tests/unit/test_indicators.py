"""Indicator math: SMA, prior-days volume average, slope, and no look-ahead."""

import numpy as np
import pandas as pd
import pytest

from app.services.indicators import calculator as calc


def _frame(prices: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    volumes = volumes if volumes is not None else [100.0] * len(prices)
    index = pd.bdate_range("2026-01-01", periods=len(prices))
    return pd.DataFrame(
        {"adjusted_close": prices, "volume": volumes},
        index=[d.date() for d in index],
    )


def test_sma_values_and_warmup():
    frame = _frame([10, 20, 30, 40, 50])
    out = calc.compute_indicators(frame, sma_short_window=3, sma_medium_window=4, sma_long_window=5)
    sma3 = out[calc.SMA_SHORT].tolist()
    assert np.isnan(sma3[0]) and np.isnan(sma3[1])  # warmup -> NaN, never partial
    assert sma3[2] == pytest.approx(20.0)  # (10+20+30)/3
    assert sma3[3] == pytest.approx(30.0)
    assert sma3[4] == pytest.approx(40.0)
    assert out[calc.SMA_LONG].tolist()[-1] == pytest.approx(30.0)  # (10+..+50)/5


def test_volume_average_uses_prior_days_only():
    frame = _frame([1] * 5, volumes=[10, 20, 30, 40, 1000])
    out = calc.compute_indicators(frame, sma_short_window=2, sma_medium_window=3,
                                  sma_long_window=4, volume_average_days=2)
    avg = out[calc.AVERAGE_VOLUME].tolist()
    # avg[t] = mean(volume[t-2], volume[t-1]) — never includes volume[t]
    assert np.isnan(avg[0]) and np.isnan(avg[1])
    assert avg[2] == pytest.approx(15.0)  # (10+20)/2
    assert avg[3] == pytest.approx(25.0)  # (20+30)/2
    assert avg[4] == pytest.approx(35.0)  # (30+40)/2 — the 1000 spike is excluded
    assert out[calc.VOLUME_RATIO].tolist()[4] == pytest.approx(1000 / 35.0)


def test_slope_formula_and_lookback():
    prices = [100.0] * 6 + [110.0] * 6
    frame = _frame(prices)
    out = calc.compute_indicators(
        frame, sma_short_window=2, sma_medium_window=3, sma_long_window=4,
        slope_lookback_days=3,
    )
    sma = out[calc.SMA_LONG]
    slope = out[calc.SMA_LONG_SLOPE]
    t = len(prices) - 1
    expected = (sma.iloc[t] / sma.iloc[t - 3] - 1.0) * 100.0
    assert slope.iloc[t] == pytest.approx(expected)
    assert slope.iloc[t] > 0  # rising series -> positive slope


def test_flat_series_has_zero_slope():
    frame = _frame([50.0] * 12)
    out = calc.compute_indicators(
        frame, sma_short_window=2, sma_medium_window=3, sma_long_window=5,
        slope_lookback_days=4,
    )
    assert out[calc.SMA_LONG_SLOPE].iloc[-1] == pytest.approx(0.0)


def test_no_lookahead_truncation_invariance():
    """Indicator values at day t are identical whether or not future rows exist."""
    rng = np.random.default_rng(7)
    prices = 100 + rng.normal(0, 1, 60).cumsum()
    volumes = rng.integers(50, 150, 60).astype(float)
    full = calc.compute_indicators(
        _frame(list(prices), list(volumes)),
        sma_short_window=5, sma_medium_window=10, sma_long_window=20,
        slope_lookback_days=5, volume_average_days=5,
    )
    cutoff = 40
    truncated = calc.compute_indicators(
        _frame(list(prices[:cutoff]), list(volumes[:cutoff])),
        sma_short_window=5, sma_medium_window=10, sma_long_window=20,
        slope_lookback_days=5, volume_average_days=5,
    )
    for col in (calc.SMA_SHORT, calc.SMA_MEDIUM, calc.SMA_LONG,
                calc.AVERAGE_VOLUME, calc.VOLUME_RATIO, calc.SMA_LONG_SLOPE):
        pd.testing.assert_series_equal(
            full[col].iloc[:cutoff], truncated[col], check_names=False
        )


def test_zero_average_volume_gives_nan_ratio_not_inf():
    frame = _frame([1] * 5, volumes=[0, 0, 0, 5, 5])
    out = calc.compute_indicators(frame, sma_short_window=2, sma_medium_window=3,
                                  sma_long_window=4, volume_average_days=2)
    ratio = out[calc.VOLUME_RATIO]
    assert not np.isinf(ratio.fillna(0)).any()


def test_duplicate_dates_deduped_by_prices_to_frame():
    class Row:
        def __init__(self, d, c, v):
            self.trade_date, self.adjusted_close, self.close = d, c, c
            self.open, self.volume = c, v

    from datetime import date
    rows = [Row(date(2026, 1, 5), 10, 100), Row(date(2026, 1, 5), 11, 110),
            Row(date(2026, 1, 6), 12, 120)]
    frame = calc.prices_to_frame(rows)
    assert len(frame) == 2
    assert frame.loc[date(2026, 1, 5), "adjusted_close"] == 11.0  # keep=last
