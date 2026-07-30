# Spec — Composable Strategy Builder & "Beat the S&P 500" Competition

Status: **draft for review** · Author: platform · Supersedes nothing (additive)

This spec extends the platform from **one hard-coded strategy**
([`sma_trend_volume`](../backend/app/services/strategies/sma_trend_volume.py)) to a
**library of building blocks users compose into their own strategies**, and turns
the competition's benchmark line into a **ranked opponent** so the explicit goal
becomes *beat the S&P 500*.

It preserves every existing invariant: exact underlying values, adjusted close by
default, trading-day lookbacks, **no look-ahead** (a signal on day `t` uses only
data available by `t`'s close; execution is the next trading day). See
[strategy-rules.md](strategy-rules.md).

---

## 1. Goals

1. Offer a **menu of indicators and conditions** users pick from and combine into
   buy/sell rule sets — the current SMA strategy becomes *one preset among many*.
2. Ship **preset templates** so no one starts from a blank page.
3. Make the **S&P 500 a first-class competitor** in every competition, ranked
   alongside user strategies, with "beat the market" KPIs (alpha, % of days
   outperforming, information ratio, up/down capture).

## 2. Non-goals (this phase)

- **Fundamental conditions** (P/E, sector, earnings-date avoidance). `market_cap`
  is currently NULL for all rows in the DB; fundamentals are a later phase once
  that data is populated. Start **price/volume/technical only**.
- Intraday indicators (VWAP, tick data) — the platform is daily-bar.
- Nested boolean trees (`(A AND B) OR C`). Phase 1 uses a **flat condition list
  with one combinator** (`all` / `any` / `at least k of`); nesting is a later add.

---

## 3. Part A — Composable rule engine (`rule_composer`)

### 3.1 How it slots into what exists

Add **one new engine class**, `RuleStrategy` (`strategy_type = "rule_composer"`),
registered beside the current one in
[`registry.py`](../backend/app/services/strategies/registry.py). It implements the
existing [`Strategy`](../backend/app/services/strategies/base.py) ABC — nothing in
the base event machinery, paper engine, backtester, or signal UI changes:

| ABC method | RuleStrategy behavior |
|---|---|
| `calculate_indicators` | Compute every indicator referenced by any operand (deduped). |
| `compute_states` | Evaluate the entry/exit condition lists vectorized → `(buy_state, sell_state)`. |
| `explain_row` | Emit one `ConditionResult` per condition — **the exact checklist the Signals UI already renders**. |

Because `explain_row` already returns `ConditionResult(label, actual, threshold,
comparison, passed)`, an arbitrary user-composed strategy renders through the
current condition-checklist UI with **zero UI changes**.

### 3.2 Parameter schema (`rule_composer` v1)

```json
{
  "entry": {
    "combine": "all",
    "at_least_k": null,
    "conditions": [
      { "key": "trend_filter",
        "left":  { "type": "price" },
        "comparison": ">",
        "right": { "type": "indicator", "name": "sma", "params": { "period": 200 } } },
      { "key": "oversold",
        "left":  { "type": "indicator", "name": "rsi", "params": { "period": 14 } },
        "comparison": "<",
        "right": { "type": "const", "value": 30 } }
    ]
  },
  "exit": {
    "combine": "any",
    "at_least_k": null,
    "conditions": [
      { "key": "overbought",
        "left":  { "type": "indicator", "name": "rsi", "params": { "period": 14 } },
        "comparison": ">",
        "right": { "type": "const", "value": 70 } }
    ],
    "risk": {
      "stop_loss_percent": 8.0,
      "trailing_stop_percent": null,
      "take_profit_percent": null,
      "max_hold_days": null
    }
  },
  "signal_mode": "transition",
  "execution_timing": "next_market_open"
}
```

**Operand types:** `price` (adjusted close), `indicator` (name + params), `const`
(number), and raw series like `volume`. **Comparisons:** `>`, `>=`, `<`, `<=`,
`cross_above`, `cross_below` (the cross operators use `shift(1)` — the engine has
the full causal frame, so this stays look-ahead-free).

**Combinator:** `all` (AND), `any` (OR), or `at_least` with `at_least_k` = k.

### 3.3 Indicator / operand library (Phase 1)

Each is a named operand with typed params; all causal (no future bars).

| Group | Operands |
|---|---|
| Trend | `sma{period}`, `ema{period}`, `ma_slope{period,lookback}`, `macd`→`{line,signal,hist}`, `adx{period}`, `donchian_high{period}`, `donchian_low{period}` |
| Momentum | `rsi{period}`, `stochastic`→`{k,d}`, `roc{period}`, `return_n{period}` |
| Volatility | `bollinger{period,k}`→`{upper,mid,lower}`, `atr{period}`, `hist_vol{period}` |
| Volume | `volume`, `avg_volume{period}` (prior days only), `volume_ratio`, `obv` |
| Price structure | `pct_from_52w_high`, `pct_from_52w_low`, `gap_percent`, `consecutive_up`, `consecutive_down` |
| Market regime | `benchmark_above_sma{symbol,period}` — a market-wide boolean ("risk-on") shared across the universe |

Reuse [`indicators/calculator.py`](../backend/app/services/indicators/calculator.py);
extend it with the new indicators. Compute each referenced indicator **once** per
frame and cache by `(name, params)`.

### 3.4 Validation (reject at strategy-create time)

- Every operand `name` is in the library; every `params` field within bounds.
- `entry.conditions` is non-empty; `at_least_k` present iff `combine == "at_least"`
  and `1 ≤ k ≤ len(conditions)`.
- Exit may be empty **only if** at least one `risk` rule is set (otherwise a
  position could never close on signal).
- Comparisons match operand arity (e.g. `cross_above` needs two series operands,
  not a const on both sides).
- `condition.key` values are unique (they anchor the persisted explanation).

### 3.5 Risk / exit rules (position-level)

`stop_loss_percent`, `trailing_stop_percent`, `take_profit_percent`,
`max_hold_days` are evaluated by the **paper/backtest execution loop** against each
open position's entry price and high-water mark — *not* by `compute_states` (which
is symbol-state, not position-state). **⚠ Open decision (§7):** confirm the paper
engine ([`paper_trading/service.py`](../backend/app/services/paper_trading/service.py)
+ its execution loop) can apply position-level exits; if not, that's a scoped
sub-task before risk rules ship. Strategy-signal exits work today.

### 3.6 Preset templates

Seed strategies users clone and tweak (clone flow already exists via
`competition.clone_account`):

1. **Trend-following** — the current SMA 20/50/150 + volume rules, re-expressed as
   `rule_composer` conditions (proves parity).
2. **Mean-reversion** — `rsi(14) < 30` AND `price > sma(200)`; exit `rsi(14) > 55`
   or `stop_loss 8%`.
3. **Breakout** — `price cross_above donchian_high(20)` AND `benchmark risk-on`;
   exit `price cross_below donchian_low(10)`.
4. **Momentum** — `return_n(126) > 0` AND `price > sma(100)`; trailing stop 15%.
5. **Buy & hold + regime filter** — hold while `benchmark_above_sma(SPY,200)`.

### 3.7 Persistence & versioning

Strategies already persist a **parameter snapshot** + `parameter_hash`. A
`rule_composer` strategy stores its full condition list in the same snapshot, so
historical signals remain explainable after edits (existing guarantee). Editing a
composed strategy creates a new snapshot/hash — never mutates an in-flight paper
account's basis.

### 3.8 API additions

- `GET /api/v1/strategy-blocks` — the indicator/operand library + comparison list +
  param bounds, so the builder UI is data-driven (no hard-coded block list in JS).
- `POST /api/v1/strategies/validate` — validate a draft rule set, return
  per-condition errors.
- `POST /api/v1/strategies/{id}/preview?symbol=AAPL` — run `explain_row` for the
  latest bar of one symbol → live "do these conditions pass right now?" preview.
  Reuses the existing explain machinery.
- Existing strategy CRUD accepts `strategy_type: "rule_composer"`.

---

## 4. Part B — Strategy builder UI

New page `/strategies/new` (and edit):

- **Block palette** grouped by the §3.3 table; drag/click to add a condition row.
- Each condition row: `left operand` · `comparison` · `right operand/const`, all
  driven by `GET /strategy-blocks`.
- Combinator selector: All / Any / At least [k].
- Separate **Entry** and **Exit** sections; risk-rule inputs (stop/trailing/TP/max
  hold).
- **Live preview panel:** pick a symbol → calls `preview` → shows the same green/red
  checklist as the Signals page, so users see their rules evaluated on real data
  before saving.
- "Start from a preset" opens one of §3.6 pre-filled.
- Save → strategy usable in scanner, backtest, paper account, and competition.

## 5. Part C — S&P 500 as a ranked competitor

### 5.1 Benchmark becomes an opponent, not a background line

Today [`competition/service.py`](../backend/app/services/competition/service.py)
fetches the benchmark and rebases it to 100 as `benchmark_curve` only. Change:

- Build a **synthetic competitor** over the competition's common window:
  `equity = initial_cash × (bench / bench[0])`, run it through the *same*
  `metrics_mod.compute_metrics` used for real accounts (buy-&-hold, zero trades).
- Insert it as a leaderboard row: `account_name: "S&P 500 (Buy & Hold)"`,
  `is_benchmark: true`, with real `total_return_pct` / `sharpe_ratio` /
  `max_drawdown_pct`, and **include it in the Sharpe-first ranking**.
- Style it distinctly in the UI as *the line to beat*; render its rank so each
  strategy is visibly above or below it.

### 5.2 "Beat the market" KPIs (per account, over the common window)

- **Alpha** — already computed as `excess_return_pct`; surface it prominently.
- **% of days outperforming** — share of days the account's rebased curve is above
  the index's rebased curve.
- **Information ratio** — `mean(daily excess) / std(daily excess) × √252`.
- **Up/down capture** — account return on index-up vs index-down days.
- **Headline verdict** — "Beating the S&P 500 by +X.X%" / "Trailing by −X.X%".

### 5.3 Fairness & integrity

- The benchmark competitor is exempt from the "same strategy" fairness dimension
  but shares the window and initial capital (it already would).
- User-composed strategies inherit the engine's **no-look-ahead / next-day
  execution** guarantee, so competition results stay honest.
- Universe is the current S&P 500 → **survivorship bias** note already surfaced for
  paper accounts; keep surfacing it.
- Optional: competition **seasons** (monthly/quarterly) whose win condition is
  literally "finish above the S&P 500 row."

---

## 6. Backward compatibility & rollout

- `sma_trend_volume` stays registered and unchanged; existing accounts/backtests
  are untouched. Preset #1 re-expresses it in `rule_composer` to prove parity
  (same signals on the same history within rounding).
- **Phase 1** — `rule_composer` engine + indicator library + validation + presets
  + `strategy-blocks`/`validate`/`preview` APIs. Backend + tests only.
- **Phase 2** — builder UI with live preview.
- **Phase 3** — S&P 500 ranked competitor + beat-the-market KPIs (smallest lift;
  can ship in parallel with Phase 2).
- **Phase 4 (later)** — position-level risk exits (if the paper engine needs work),
  nested boolean groups, fundamentals.

## 7. Open decisions (need your call)

1. **Rule expressiveness** — start with flat `all/any/k-of` (recommended) or invest
   in nested AND/OR groups now?
2. **Risk exits** — does the current paper execution loop support position-level
   stop-loss / trailing / take-profit, or is that a Phase-1 sub-task? (Affects §3.5
   scope.)
3. **Benchmark symbol & data** — which daily series backs "S&P 500": `SPY`,
   `^GSPC`, or an index you already store reliably? The competitor row needs a
   gap-free daily series over every competition window.
4. **Fundamentals** — confirm deferring P/E / sector / earnings until `market_cap`
   and fundamentals data are populated.

## 8. Testing

- Unit: each new indicator vs a hand-computed fixture; causality (no future bar
  leaks); `rule_composer` parity with `sma_trend_volume` on a shared fixture.
- Unit: validation rejects malformed rule sets (unknown block, empty entry, bad k,
  arity mismatch).
- Integration (`*_db.py`, gated on `DATABASE_URL`): `strategy-blocks`, `validate`,
  `preview`, and the benchmark competitor appearing ranked in `leaderboard()` with
  finite metrics and correct alpha sign.
