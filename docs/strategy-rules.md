# Strategy rules — SMA Trend and Volume Strategy v1

All comparisons use **exact underlying values** (never rounded chart pixels)
and **adjusted close** by default, so splits and dividends do not create false
signals.

## Parameters (defaults)

```json
{
  "sma_short_window": 20,
  "sma_medium_window": 50,
  "sma_long_window": 150,
  "sma_150_slope_lookback_days": 10,
  "sma_150_min_slope_percent": 0,
  "volume_average_days": 10,
  "volume_multiplier": 1.0,
  "minimum_market_cap": null,
  "maximum_market_cap": null,
  "history_period_years": 20,
  "chart_period_years": 5,
  "signal_mode": "transition",
  "execution_timing": "next_market_open"
}
```

All lookbacks are **trading days**, not calendar days.

## Buy state — all four conditions true on day `t`

1. **SMA 150 flat or rising**
   `((SMA150[t] / SMA150[t − slope_lookback_days]) − 1) × 100 ≥ sma_150_min_slope_percent`
   (default minimum slope 0%)
2. **Price above SMA 150** — `AdjClose[t] > SMA150[t]` (strict)
3. **SMA 20 above SMA 50** — `SMA20[t] > SMA50[t]` (strict)
4. **Volume above its recent average** —
   `Volume[t] ≥ mean(Volume[t−N … t−1]) × volume_multiplier` with
   `N = volume_average_days`. The average uses **prior completed days only**;
   day `t`'s volume is never inside its own comparison average.

## Buy event vs buy state

- `transition` mode (default): a BUY event fires only when
  `buy_state[t] AND NOT buy_state[t−1]`.
- `scan` mode: lists every stock currently satisfying the buy conditions,
  even if the state started earlier.

## Sell state — both conditions true on day `t`

1. **Price below SMA 150** — `AdjClose[t] < SMA150[t]`
2. **SMA 20 below SMA 50** — `SMA20[t] < SMA50[t]`

A SELL event fires on the false→true transition, same as buys. Paper accounts
execute a sell only when they own the stock; the market scanner may still show
the signal.

## Conflict handling

1. If a sell condition is true for an open position, the sell is processed.
2. The same account never buys and sells the same stock on the same
   execution date.
3. Skipped orders always record a reason.

## Signal persistence

Every signal stores the exact values of every condition (adjusted close,
SMA 20/50/150, SMA 150 slope, volume, average volume, volume ratio) plus the
full parameter snapshot, so any historical signal can be explained later even
after parameters change.
