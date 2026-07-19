# Backtesting assumptions

## Execution model (Phase 6, implemented)

- Signals are recomputed from stored prices with the run's own parameters
  (never read from the signals table), always in transition mode — scan mode
  would re-buy daily, which is meaningless without pyramiding.
- A day-t signal fills at the stock's **next trading day's open** (its own
  calendar, so per-stock missing days delay the fill instead of inventing a
  price). Fills use the **split-adjusted open**: `open × adjusted_close/close`,
  so trades across splits stay on the same price basis as the signals.
- Slippage (default 0.05%) works against the trade on both sides; commission
  is a flat amount per fill. Sells execute before buys each day (freed cash is
  usable the same day); a stock sold today is never re-bought today.
- Concurrent buy candidates are ranked volume ratio desc, SMA-long slope desc,
  then symbol — the spec's deterministic ordering.
- Position sizing (`equal_weight`): `position_size_percent` of the **previous
  close's** total equity (known before the open — no look-ahead), capped by
  available cash, so cash can never go negative. Whole shares by default;
  fractional (4 dp) optional. No pyramiding, shorts, or leverage.
- Signals that do not become trades are recorded with a reason
  (max_positions, insufficient_cash, already_holding, same_day_conflict,
  no_next_open, no_price_at_execution); sell signals for never-held stocks are
  summarized in counts only.
- Daily equity marks positions at the last known adjusted close on or before
  that day. Positions still open at the end are reported as OPEN with
  unrealized P&L — no exit is invented.
- Benchmark (default `^GSPC`) is stored like any tracked symbol (auto-added,
  auto-synced; excluded from the scanner and signal scans) and rebased to
  starting capital for comparison. If unavailable, benchmark metrics are null.
- Metrics conventions: 252 trading days/year, risk-free rate 0; Sortino's
  downside deviation is `sqrt(mean(min(r,0)^2))`; trade statistics cover
  closed trades; exposure is the average invested fraction of equity;
  turnover is `((buys+sells)/2) / average equity / years`.
- Determinism: reruns with identical data + configuration produce
  bit-identical results (tests enforce this, plus truncation invariance:
  shortening the window never changes earlier entries).

## Paper-trading execution (Phase 7, implemented)

Paper accounts are LIVE simulations that advance one real market day at a
time (with automatic catch-up from any past start date), so they differ from
backtests in one deliberate way: they trade **raw** prices like a real broker,
not back-adjusted ones.

- Fills: the first trading day after the signal with data for the stock, at
  that day's raw open, slippage against the trade, flat commission per fill.
  Sells before buys; ranked buys (volume ratio desc, slope desc, symbol); no
  pyramiding/shorts/leverage; sizing from the previous close's equity capped
  by cash. Same ordering rules as the backtester.
- **Splits** multiply the position quantity and divide the average entry
  price on the ex-date (cost basis unchanged) — without this, raw-price
  accounts would show huge false losses on every split. Odd lots keep
  fractional remainders (real brokers pay cash in lieu).
- **Dividends** credit cash on the ex-date (quantity × dividend per share).
  Pay-date timing is ignored — a small, disclosed simplification.
- Each account freezes its strategy parameter snapshot (and hash) at
  creation; its signal set is detected independently, so accounts with
  different parameters trade different signals. Accounts never share state.
- Orders are the audit trail: PENDING → EXECUTED / REJECTED (reason kept:
  max_positions, insufficient_cash, already_holding, same_day_conflict,
  filtered_market_cap) / CANCELLED (no data for 15+ days). At most one order
  per signal per account, enforced by the database.
- Daily equity snapshots (cash, positions value, total, daily/cumulative
  return, drawdown) are unique per day — reprocessing is a no-op.
- Performance statistics reuse the backtesting metrics module, so accounts
  and backtests are directly comparable (Phase 8's fair-comparison basis).

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
