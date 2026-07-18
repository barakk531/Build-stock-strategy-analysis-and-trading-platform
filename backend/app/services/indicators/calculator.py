"""Vectorized indicator computation. No look-ahead by construction:

- SMAs use trailing rolling windows over the adjusted close.
- The volume average covers the PRIOR N completed days only (shift(1) before
  rolling), so day t's volume is never inside its own comparison average.
- The SMA-long slope compares SMA[t] against SMA[t - lookback] in trading days.

Values are NaN until a window has enough history (min_periods == window), so
short histories simply produce no state instead of a wrong one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Canonical output column names (parameter-independent).
SMA_SHORT = "sma_short"
SMA_MEDIUM = "sma_medium"
SMA_LONG = "sma_long"
AVERAGE_VOLUME = "average_volume"
VOLUME_RATIO = "volume_ratio"
SMA_LONG_SLOPE = "sma_long_slope_percent"


def prices_to_frame(rows: list) -> pd.DataFrame:
    """Build the calculator input frame from DailyPrice rows (chronological)."""
    def col(name: str) -> list[float]:
        return [
            float(value) if (value := getattr(r, name)) is not None else np.nan for r in rows
        ]

    frame = pd.DataFrame(
        {
            "trade_date": [r.trade_date for r in rows],
            "adjusted_close": col("adjusted_close"),
            "close": col("close"),
            "open": col("open"),
            "volume": col("volume"),
        }
    )
    frame = frame.set_index("trade_date")
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def compute_indicators(
    frame: pd.DataFrame,
    *,
    sma_short_window: int = 20,
    sma_medium_window: int = 50,
    sma_long_window: int = 150,
    slope_lookback_days: int = 10,
    volume_average_days: int = 10,
) -> pd.DataFrame:
    """Return a copy of `frame` with indicator columns appended.

    `frame` needs `adjusted_close` and `volume` columns indexed by trade date,
    ascending and unique.
    """
    out = frame.copy()
    price = out["adjusted_close"].astype(float)
    volume = out["volume"].astype(float)

    out[SMA_SHORT] = price.rolling(sma_short_window, min_periods=sma_short_window).mean()
    out[SMA_MEDIUM] = price.rolling(sma_medium_window, min_periods=sma_medium_window).mean()
    out[SMA_LONG] = price.rolling(sma_long_window, min_periods=sma_long_window).mean()

    # Prior completed days only — never the current day's volume.
    prior = volume.shift(1)
    out[AVERAGE_VOLUME] = prior.rolling(volume_average_days, min_periods=volume_average_days).mean()
    ratio = volume / out[AVERAGE_VOLUME]
    out[VOLUME_RATIO] = ratio.replace([np.inf, -np.inf], np.nan)

    shifted = out[SMA_LONG].shift(slope_lookback_days)
    out[SMA_LONG_SLOPE] = (out[SMA_LONG] / shifted - 1.0) * 100.0

    return out
