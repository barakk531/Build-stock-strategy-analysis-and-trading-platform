# Backtesting assumptions

## Look-ahead bias prevention (mandatory)

- A day-`t` signal is computed only from information available by day `t`'s
  close. Indicators never reference future rows.
- **Execution happens at the next trading day's open** by default
  (`execution_timing = "next_market_open"`). The close that produced a signal
  is never the fill price.
- If the next open is unavailable (delisting, end of data), no price is
  invented — the order stays unexecuted with a recorded reason.
- The volume average compares day `t` against the mean of the **prior** `N`
  completed days, excluding day `t` itself.
- Later execution modes (next-day close; same-day close, which is unrealistic
  unless the signal is computed before the close) will be labeled accordingly.

## Survivorship bias (version 1 limitation)

Version 1 backtests run over the **current** S&P 500 constituents projected
into the past. Companies that were removed (bankruptcies, acquisitions,
demotions) are missing, which inflates results. This is disclosed in the UI.
A survivorship-bias-aware historical membership universe is future work.

## Market capitalization

Market-cap filters use **today's** market cap (no historical shares
outstanding data), so applying them to old dates introduces look-ahead. Market
cap is therefore a stock-universe filter, not a historical daily indicator.

## Prices

Indicators and backtests use **split-adjusted** data (adjusted close) so
splits do not create false signals or false profits.

## Determinism

Identical data + identical parameters must produce identical signals, trades,
and statistics. Phase 6 adds tests enforcing this, plus: no negative cash
without leverage, no sells without a position, no double buys without
pyramiding, and correct handling of missing trading days.

## Costs

Commission and slippage are configurable per backtest / paper account
(defaults: commission 0, slippage 0.05%). Zero-commission defaults still
overstate real-world results for large portfolios.
