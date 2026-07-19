"""Portfolio simulation over pre-computed signals. Deterministic by design.

Execution model (spec §8/§13/§15):
- A day-t signal creates an order for the stock's NEXT trading day; it fills at
  that day's split-adjusted open with slippage applied (buys pay more, sells
  receive less) plus a flat commission. The close that produced the signal is
  never a fill price.
- Sells execute before buys each day (freed cash is usable the same day), and
  a stock sold today is never re-bought today.
- Multiple buy candidates on one day are ranked volume ratio desc, SMA-long
  slope desc, then symbol — the spec's deterministic ordering.
- Position sizing: position_size_percent of the PREVIOUS close's total equity
  (known before the open — no look-ahead), capped by available cash, so cash
  can never go negative. No pyramiding, no shorts, no leverage.
- Signals with no next trading day in the data stay unexecuted with reason
  no_next_open — no price is ever invented.
- Daily equity marks positions at the last known adjusted close on or before
  that day (forward-filled), which handles per-stock missing trading days.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.services.backtesting.config import BacktestConfig

BUY = "BUY"
SELL = "SELL"

# Guardrail for the detailed skip table; the summary always has full counts.
MAX_SKIP_ROWS = 20_000

# Skip reasons
R_MAX_POSITIONS = "max_positions"
R_INSUFFICIENT_CASH = "insufficient_cash"
R_ALREADY_HOLDING = "already_holding"
R_SAME_DAY_CONFLICT = "same_day_conflict"
R_NO_NEXT_OPEN = "no_next_open"
R_NO_PRICE = "no_price_at_execution"
R_SELL_NO_POSITION = "sell_no_position"  # summary-only (would dominate the table)


class BacktestDataError(ValueError):
    """No usable price data for the requested universe/date range."""


@dataclass
class OrderIntent:
    """A signal translated into a pending order for its execution date."""

    symbol: str
    side: str  # BUY | SELL
    signal_date: date
    execution_date: date | None
    volume_ratio: float | None = None
    slope: float | None = None


@dataclass
class TradeResult:
    symbol: str
    quantity: float
    entry_signal_date: date
    entry_date: date
    entry_price: float
    commission_paid: float
    status: str = "OPEN"
    exit_signal_date: date | None = None
    exit_date: date | None = None
    exit_price: float | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    holding_days: int | None = None


@dataclass
class SkipResult:
    symbol: str
    signal_date: date
    signal_type: str
    reason: str
    detail: str | None = None


@dataclass
class _Position:
    quantity: float
    entry_signal_date: date
    entry_date: date
    entry_price: float  # effective fill (open + slippage)
    entry_commission: float
    cost_total: float  # quantity * entry_price + commission


@dataclass
class EngineResult:
    trades: list[TradeResult]
    skips: list[SkipResult]
    skip_summary: dict[str, int]
    equity: pd.DataFrame  # index: date; columns: cash, positions_value, equity
    open_positions: list[dict]
    buy_notional: float = 0.0
    sell_notional: float = 0.0
    executed_buys: int = 0
    executed_sells: int = 0
    skipped_signals: int = field(default=0)


def _rank_key(order: OrderIntent) -> tuple:
    vr = order.volume_ratio if order.volume_ratio is not None else float("-inf")
    slope = order.slope if order.slope is not None else float("-inf")
    return (-vr, -slope, order.symbol)


def _floor_quantity(raw: float, fractional: bool) -> float:
    if fractional:
        return math.floor(raw * 10_000) / 10_000  # 4 dp, never exceeding budget
    return float(math.floor(raw))


def run_simulation(
    config: BacktestConfig,
    panel: dict[str, pd.DataFrame],
    orders: list[OrderIntent],
) -> EngineResult:
    """Simulate the portfolio.

    `panel` maps symbol -> frame indexed by trade date (ascending, within
    [start_date, end_date]) with columns adj_open and adj_close.
    `orders` carry signal dates within the window; execution dates were derived
    from each stock's own trading calendar (None = no next bar exists).
    """
    calendar = sorted({d for frame in panel.values() for d in frame.index})
    if not calendar:
        raise BacktestDataError("no price data in the selected universe and date range")

    symbols = sorted(panel.keys())
    opens = pd.DataFrame(
        {sym: panel[sym]["adj_open"].reindex(calendar) for sym in symbols}, index=calendar
    )
    closes = pd.DataFrame(
        {sym: panel[sym]["adj_close"].reindex(calendar) for sym in symbols}, index=calendar
    ).ffill()

    skips: list[SkipResult] = []
    skip_summary: dict[str, int] = {}

    def record_skip(order: OrderIntent, reason: str, detail: str | None = None) -> None:
        skip_summary[reason] = skip_summary.get(reason, 0) + 1
        if reason != R_SELL_NO_POSITION and len(skips) < MAX_SKIP_ROWS:
            skips.append(SkipResult(order.symbol, order.signal_date, order.side, reason, detail))

    pending: dict[date, list[OrderIntent]] = {}
    last_day = calendar[-1]
    for order in orders:
        if order.execution_date is None or order.execution_date > last_day:
            record_skip(order, R_NO_NEXT_OPEN)
            continue
        pending.setdefault(order.execution_date, []).append(order)

    slip = config.slippage_percent / 100.0
    commission = config.commission_per_trade
    size_fraction = config.position_size_percent / 100.0
    min_quantity = 0.0001 if config.allow_fractional_shares else 1.0

    cash = config.initial_cash
    equity_mark = config.initial_cash  # previous close equity, sizing basis
    positions: dict[str, _Position] = {}
    trades: list[TradeResult] = []
    snapshots: list[tuple[date, float, float, float]] = []
    buy_notional = 0.0
    sell_notional = 0.0
    executed_buys = 0
    executed_sells = 0

    for day in calendar:
        todays = pending.pop(day, [])
        sells = sorted(
            (o for o in todays if o.side == SELL), key=lambda o: o.symbol
        )
        buys = sorted((o for o in todays if o.side == BUY), key=_rank_key)

        sold_today: set[str] = set()
        for order in sells:
            position = positions.get(order.symbol)
            if position is None:
                record_skip(order, R_SELL_NO_POSITION)
                continue
            open_price = opens.at[day, order.symbol]
            if pd.isna(open_price):
                record_skip(order, R_NO_PRICE)
                continue
            fill = float(open_price) * (1.0 - slip)
            gross = position.quantity * fill
            proceeds = gross - commission
            cash += proceeds
            sell_notional += gross
            executed_sells += 1
            pnl = proceeds - position.cost_total
            trades.append(
                TradeResult(
                    symbol=order.symbol,
                    quantity=position.quantity,
                    entry_signal_date=position.entry_signal_date,
                    entry_date=position.entry_date,
                    entry_price=position.entry_price,
                    commission_paid=position.entry_commission + commission,
                    status="CLOSED",
                    exit_signal_date=order.signal_date,
                    exit_date=day,
                    exit_price=fill,
                    pnl=pnl,
                    pnl_percent=(pnl / position.cost_total * 100.0)
                    if position.cost_total > 0
                    else None,
                    holding_days=(day - position.entry_date).days,
                )
            )
            del positions[order.symbol]
            sold_today.add(order.symbol)

        for order in buys:
            if order.symbol in positions:
                record_skip(order, R_ALREADY_HOLDING)
                continue
            if order.symbol in sold_today:
                record_skip(order, R_SAME_DAY_CONFLICT)
                continue
            if len(positions) >= config.max_open_positions:
                record_skip(order, R_MAX_POSITIONS)
                continue
            open_price = opens.at[day, order.symbol]
            if pd.isna(open_price):
                record_skip(order, R_NO_PRICE)
                continue
            fill = float(open_price) * (1.0 + slip)
            target = equity_mark * size_fraction
            budget = min(target, cash - commission)
            quantity = _floor_quantity(budget / fill, config.allow_fractional_shares)
            if quantity < min_quantity or budget <= 0:
                record_skip(order, R_INSUFFICIENT_CASH, detail=f"cash {cash:.2f}")
                continue
            gross = quantity * fill
            cost = gross + commission
            cash -= cost  # >= 0 by construction: gross <= cash - commission
            buy_notional += gross
            executed_buys += 1
            positions[order.symbol] = _Position(
                quantity=quantity,
                entry_signal_date=order.signal_date,
                entry_date=day,
                entry_price=fill,
                entry_commission=commission,
                cost_total=cost,
            )

        positions_value = 0.0
        for sym, position in positions.items():
            mark = closes.at[day, sym]
            if not pd.isna(mark):
                positions_value += position.quantity * float(mark)
        equity = cash + positions_value
        snapshots.append((day, cash, positions_value, equity))
        equity_mark = equity

    equity_frame = pd.DataFrame(
        snapshots, columns=["trade_date", "cash", "positions_value", "equity"]
    ).set_index("trade_date")

    open_positions = []
    for sym in sorted(positions):
        position = positions[sym]
        mark = closes.at[last_day, sym]
        mark_value = None if pd.isna(mark) else position.quantity * float(mark)
        trades.append(
            TradeResult(
                symbol=sym,
                quantity=position.quantity,
                entry_signal_date=position.entry_signal_date,
                entry_date=position.entry_date,
                entry_price=position.entry_price,
                commission_paid=position.entry_commission,
                status="OPEN",
            )
        )
        open_positions.append(
            {
                "symbol": sym,
                "quantity": position.quantity,
                "entry_date": position.entry_date.isoformat(),
                "entry_price": round(position.entry_price, 4),
                "last_price": None if pd.isna(mark) else round(float(mark), 4),
                "market_value": None if mark_value is None else round(mark_value, 2),
                "unrealized_pnl": None
                if mark_value is None
                else round(mark_value - position.cost_total, 2),
            }
        )

    trades.sort(key=lambda t: (t.entry_date, t.symbol))
    return EngineResult(
        trades=trades,
        skips=skips,
        skip_summary=skip_summary,
        equity=equity_frame,
        open_positions=open_positions,
        buy_notional=buy_notional,
        sell_notional=sell_notional,
        executed_buys=executed_buys,
        executed_sells=executed_sells,
        skipped_signals=sum(skip_summary.values()),
    )
