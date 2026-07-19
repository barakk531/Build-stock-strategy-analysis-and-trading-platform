"""Paper-account daily processing: signals → orders → fills → snapshots.

Each ACTIVE account replays forward from the day after its last equity
snapshot (or its start date) through the latest stored trade date, one market
day at a time:

1. Apply splits and dividends to held positions (splits multiply quantity and
   divide the entry price — cost basis unchanged; dividends credit cash on the
   ex-date). Live accounts trade RAW prices like a real broker, so split
   handling is what keeps P&L truthful.
2. Execute due pending orders at the day's raw open: a day-t signal fills on
   the first trading day after t with data for that stock — never the signal
   close, never an invented price. Slippage works against the trade; a flat
   commission applies per fill. Sells run before buys; a stock sold today is
   never re-bought today. Buy candidates rank volume ratio desc, slope desc,
   then symbol (spec §13). Sizing is position_size_percent of the previous
   close's equity, capped by cash — cash can never go negative. Rejections
   keep the order row with a reason.
3. Create orders from the day's signals for this account's strategy +
   parameter hash (each account owns an independent signal set; the unique
   (account, signal) index makes reruns duplicate-free). Sell signals for
   stocks the account does not hold create nothing (counted only).
4. Write the equity snapshot (cash, positions value, total, daily/cumulative
   return, drawdown vs the account's running peak).

The whole replay commits atomically per account, so a crash resumes cleanly;
accounts never touch each other's state (spec Phase 7 acceptance).
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.daily_price import DailyPrice
from app.models.paper import AccountEquitySnapshot, PaperAccount, PaperOrder, PaperPosition
from app.models.signal import Signal
from app.models.stock import Stock
from app.services.paper_trading.config import AccountSettings
from app.services.signals import detector

logger = logging.getLogger(__name__)

BUY = "BUY"
SELL = "SELL"

# Cancel pending orders with no fill data for this many calendar days.
_STALE_ORDER_DAYS = 15


class _PositionState:
    __slots__ = ("row", "quantity", "entry_price", "cost_basis")

    def __init__(self, row: PaperPosition):
        self.row = row
        self.quantity = float(row.quantity)
        self.entry_price = float(row.average_entry_price)
        self.cost_basis = float(row.cost_basis)


def _market_calendar(db: Session, start: date, end: date) -> list[date]:
    rows = db.scalars(
        select(DailyPrice.trade_date)
        .where(DailyPrice.trade_date >= start, DailyPrice.trade_date <= end)
        .distinct()
        .order_by(DailyPrice.trade_date)
    )
    return list(rows)


def _load_frames(
    db: Session, stock_ids: set[int], start: date, end: date
) -> dict[int, dict[date, tuple]]:
    """stock_id -> {date: (open, close, dividend, split)} raw prices."""
    if not stock_ids:
        return {}
    rows = db.execute(
        select(
            DailyPrice.stock_id,
            DailyPrice.trade_date,
            DailyPrice.open,
            DailyPrice.close,
            DailyPrice.dividend,
            DailyPrice.stock_split,
        ).where(
            DailyPrice.stock_id.in_(stock_ids),
            DailyPrice.trade_date >= start,
            DailyPrice.trade_date <= end,
        )
    ).all()
    frames: dict[int, dict[date, tuple]] = {}
    for stock_id, trade_date, open_, close, dividend, split in rows:
        frames.setdefault(stock_id, {})[trade_date] = (
            None if open_ is None else float(open_),
            None if close is None else float(close),
            float(dividend or 0),
            float(split or 0),
        )
    return frames


def _rank_values(signal: Signal) -> tuple[float, float]:
    values = (signal.conditions_json or {}).get("values") or {}
    vr = values.get("volume_ratio")
    slope = values.get("sma_long_slope_percent")
    return (
        float(vr) if vr is not None else float("-inf"),
        float(slope) if slope is not None else float("-inf"),
    )


def _floor_quantity(raw: float, fractional: bool) -> float:
    if fractional:
        return math.floor(raw * 10_000) / 10_000
    return float(math.floor(raw))


def ensure_signals(db: Session, account: PaperAccount) -> None:
    """Make sure this account's parameter set has signals through the latest
    data day (full history on first use; incremental afterwards)."""
    latest = db.scalar(select(func.max(DailyPrice.trade_date)))
    if latest is None:
        return
    exists = db.scalar(
        select(Signal.id)
        .where(
            Signal.strategy_id == account.strategy_id,
            Signal.parameter_hash == account.parameter_hash,
            Signal.trade_date == latest,
        )
        .limit(1)
    )
    if exists is None:
        detector.scan_all(
            db,
            strategy_id=account.strategy_id,
            parameters=account.strategy_parameter_snapshot_json,
        )


def process_account(
    db: Session, account: PaperAccount, *, through: date | None = None
) -> dict:
    """Replay one account forward. Idempotent: reruns process nothing new."""
    if account.status != "ACTIVE":
        return {"account_id": account.id, "skipped": account.status}

    latest_data = db.scalar(select(func.max(DailyPrice.trade_date)))
    if latest_data is None:
        return {"account_id": account.id, "skipped": "no price data"}
    end = min(through or latest_data, latest_data)

    last_snapshot = db.scalar(
        select(func.max(AccountEquitySnapshot.snapshot_date)).where(
            AccountEquitySnapshot.paper_account_id == account.id
        )
    )
    replay_start = (
        last_snapshot + timedelta(days=1) if last_snapshot else account.start_date
    )
    if replay_start > end:
        return {"account_id": account.id, "processed_days": 0}

    calendar = _market_calendar(db, replay_start, end)
    if not calendar:
        return {"account_id": account.id, "processed_days": 0}

    settings = AccountSettings.model_validate(account.settings_json or {})
    slip = settings.slippage_percent / 100.0
    commission = settings.commission_per_trade
    size_fraction = settings.position_size_percent / 100.0
    min_quantity = 0.0001 if settings.allow_fractional_shares else 1.0

    # --- load account state ---------------------------------------------------
    open_positions: dict[int, _PositionState] = {
        p.stock_id: _PositionState(p)
        for p in db.scalars(
            select(PaperPosition).where(
                PaperPosition.paper_account_id == account.id,
                PaperPosition.status == "OPEN",
            )
        )
    }
    pending: list[PaperOrder] = list(
        db.scalars(
            select(PaperOrder).where(
                PaperOrder.paper_account_id == account.id,
                PaperOrder.status == "PENDING",
            )
        )
    )
    ordered_signal_ids: set[int] = {
        sid
        for sid in db.scalars(
            select(PaperOrder.signal_id).where(
                PaperOrder.paper_account_id == account.id,
                PaperOrder.signal_id.isnot(None),
            )
        )
    }

    signals = list(
        db.scalars(
            select(Signal)
            .where(
                Signal.strategy_id == account.strategy_id,
                Signal.parameter_hash == account.parameter_hash,
                Signal.trade_date >= replay_start,
                Signal.trade_date <= end,
            )
            .order_by(Signal.trade_date, Signal.signal_type, Signal.id)
        )
    )
    signals_by_date: dict[date, list[Signal]] = {}
    for signal in signals:
        signals_by_date.setdefault(signal.trade_date, []).append(signal)

    rank_by_signal: dict[int, tuple[float, float]] = {s.id: _rank_values(s) for s in signals}
    for order in pending:  # carried-over orders need rank values too
        if order.signal_id is not None and order.signal_id not in rank_by_signal:
            signal = db.get(Signal, order.signal_id)
            if signal is not None:
                rank_by_signal[signal.id] = _rank_values(signal)

    stock_ids_needed = (
        set(open_positions)
        | {o.stock_id for o in pending}
        | {s.stock_id for s in signals}
    )
    frames = _load_frames(db, stock_ids_needed, replay_start - timedelta(days=30), end)
    stock_meta: dict[int, Stock] = {
        s.id: s
        for s in db.scalars(select(Stock).where(Stock.id.in_(stock_ids_needed)))
    }
    last_close: dict[int, float] = {}  # forward-filled raw close per stock
    for stock_id, frame in frames.items():
        for d in sorted(frame):
            if d < replay_start and frame[d][1] is not None:
                last_close[stock_id] = frame[d][1]

    cash = float(account.cash_balance)
    prev_equity = float(
        db.scalar(
            select(AccountEquitySnapshot.total_equity).where(
                AccountEquitySnapshot.paper_account_id == account.id,
                AccountEquitySnapshot.snapshot_date == last_snapshot,
            )
        )
        or account.initial_cash
    )
    peak = float(
        db.scalar(
            select(func.max(AccountEquitySnapshot.total_equity)).where(
                AccountEquitySnapshot.paper_account_id == account.id
            )
        )
        or 0.0
    )
    initial = float(account.initial_cash)

    counters = {
        "executed_buys": 0,
        "executed_sells": 0,
        "rejected_orders": 0,
        "orders_created": 0,
        "splits_applied": 0,
        "dividends_credited": 0,
        "sell_signals_ignored": 0,
        "cancelled_stale": 0,
    }

    def day_row(stock_id: int, day: date) -> tuple | None:
        return frames.get(stock_id, {}).get(day)

    def reject(order: PaperOrder, reason: str) -> None:
        order.status = "REJECTED"
        order.rejection_reason = reason
        counters["rejected_orders"] += 1

    for day in calendar:
        # 1) corporate actions on held positions
        for stock_id, state in open_positions.items():
            row = day_row(stock_id, day)
            if row is None:
                continue
            _, close, dividend, split = row
            if split and split > 0 and split != 1.0:
                state.quantity *= split
                state.entry_price /= split
                counters["splits_applied"] += 1
            if dividend > 0:
                cash += state.quantity * dividend
                counters["dividends_credited"] += 1
            if close is not None:
                last_close[stock_id] = close

        # 2) execute due pending orders (sells first, then ranked buys)
        due: list[PaperOrder] = []
        still_pending: list[PaperOrder] = []
        for order in pending:
            row = day_row(order.stock_id, day)
            if day > order.signal_date and row is not None and row[0] is not None:
                due.append(order)
            elif (day - order.signal_date).days > _STALE_ORDER_DAYS:
                order.status = "CANCELLED"
                order.rejection_reason = "stale_no_data"
                counters["cancelled_stale"] += 1
            else:
                still_pending.append(order)
        pending = still_pending

        sells = sorted((o for o in due if o.side == SELL), key=lambda o: o.symbol)
        buys = sorted(
            (o for o in due if o.side == BUY),
            key=lambda o: (
                -(rank_by_signal.get(o.signal_id, (float("-inf"),) * 2)[0]),
                -(rank_by_signal.get(o.signal_id, (float("-inf"),) * 2)[1]),
                o.symbol,
            ),
        )
        sold_today: set[int] = set()

        for order in sells:
            state = open_positions.get(order.stock_id)
            if state is None:
                reject(order, "not_held")
                continue
            open_price = day_row(order.stock_id, day)[0]
            fill = open_price * (1.0 - slip)
            gross = state.quantity * fill
            proceeds = gross - commission
            cash += proceeds
            realized = proceeds - state.cost_basis

            position = state.row
            position.quantity = round(state.quantity, 4)
            position.average_entry_price = round(state.entry_price, 4)
            position.closed_at = day
            position.status = "CLOSED"
            position.realized_pnl = round(realized, 2)

            order.status = "EXECUTED"
            order.quantity = round(state.quantity, 4)
            order.executed_at = day
            order.execution_price = round(fill, 4)
            order.commission = round(commission, 4)
            order.slippage = round(state.quantity * open_price * slip, 4)

            del open_positions[order.stock_id]
            sold_today.add(order.stock_id)
            counters["executed_sells"] += 1

        for order in buys:
            if order.stock_id in open_positions:
                reject(order, "already_holding")
                continue
            if order.stock_id in sold_today:
                reject(order, "same_day_conflict")
                continue
            if len(open_positions) >= settings.maximum_open_positions:
                reject(order, "max_positions")
                continue
            open_price = day_row(order.stock_id, day)[0]
            fill = open_price * (1.0 + slip)
            budget = min(prev_equity * size_fraction, cash - commission)
            quantity = _floor_quantity(budget / fill, settings.allow_fractional_shares)
            if quantity < min_quantity or budget <= 0:
                reject(order, "insufficient_cash")
                continue
            gross = quantity * fill
            cost = gross + commission
            cash -= cost  # >= 0 by construction

            position = PaperPosition(
                paper_account_id=account.id,
                stock_id=order.stock_id,
                symbol=order.symbol,
                quantity=round(quantity, 4),
                average_entry_price=round(fill, 4),
                cost_basis=round(cost, 2),
                opened_at=day,
                status="OPEN",
            )
            db.add(position)
            open_positions[order.stock_id] = _PositionState(position)

            order.status = "EXECUTED"
            order.quantity = round(quantity, 4)
            order.executed_at = day
            order.execution_price = round(fill, 4)
            order.commission = round(commission, 4)
            order.slippage = round(quantity * open_price * slip, 4)
            counters["executed_buys"] += 1

        # 3) create orders from today's signals
        for signal in signals_by_date.get(day, ()):
            if signal.id in ordered_signal_ids:
                continue
            ordered_signal_ids.add(signal.id)
            stock = stock_meta.get(signal.stock_id)
            if stock is None:
                continue

            if signal.signal_type == SELL:
                if signal.stock_id not in open_positions:
                    # The strategy exited before we entered: cancel any
                    # not-yet-filled BUY for this stock instead of buying into
                    # a position the strategy already wants out of.
                    superseded = [
                        o for o in pending if o.stock_id == signal.stock_id and o.side == BUY
                    ]
                    for buy_order in superseded:
                        buy_order.status = "CANCELLED"
                        buy_order.rejection_reason = "superseded_by_sell"
                        pending.remove(buy_order)
                        counters["rejected_orders"] += 1
                    if not superseded:
                        counters["sell_signals_ignored"] += 1
                    continue
                if any(o.stock_id == signal.stock_id and o.side == SELL for o in pending):
                    continue  # a sell is already on its way
            order = PaperOrder(
                paper_account_id=account.id,
                stock_id=signal.stock_id,
                symbol=stock.symbol,
                signal_id=signal.id,
                side=signal.signal_type,
                signal_date=signal.trade_date,
                scheduled_execution_date=signal.execution_date,
                status="PENDING",
            )
            if signal.signal_type == BUY:
                cap = stock.market_cap
                below_min = settings.minimum_market_cap is not None and (
                    cap is None or cap < settings.minimum_market_cap
                )
                above_max = settings.maximum_market_cap is not None and (
                    cap is None or cap > settings.maximum_market_cap
                )
                if below_min or above_max:
                    order.status, order.rejection_reason = "REJECTED", "filtered_market_cap"
                    counters["rejected_orders"] += 1
                elif signal.stock_id in open_positions:
                    order.status, order.rejection_reason = "REJECTED", "already_holding"
                    counters["rejected_orders"] += 1
            db.add(order)
            if order.status == "PENDING":
                pending.append(order)
                counters["orders_created"] += 1

        # 4) end-of-day equity snapshot
        positions_value = 0.0
        for stock_id, state in open_positions.items():
            mark = last_close.get(stock_id)
            if mark is None:
                mark = state.cost_basis / state.quantity if state.quantity else 0.0
            positions_value += state.quantity * mark
        equity = cash + positions_value
        peak = max(peak, equity)
        db.add(
            AccountEquitySnapshot(
                paper_account_id=account.id,
                snapshot_date=day,
                cash=round(cash, 2),
                positions_value=round(positions_value, 2),
                total_equity=round(equity, 2),
                daily_return=round(equity / prev_equity - 1.0, 6) if prev_equity > 0 else None,
                cumulative_return=round(equity / initial - 1.0, 6),
                drawdown=round(equity / peak - 1.0, 6) if peak > 0 else 0,
            )
        )
        prev_equity = equity

    # write back still-open positions (split adjustments) and account cash
    for state in open_positions.values():
        state.row.quantity = round(state.quantity, 4)
        state.row.average_entry_price = round(state.entry_price, 4)
    account.cash_balance = round(cash, 2)
    db.commit()

    counters.update(
        {"account_id": account.id, "processed_days": len(calendar), "through": end.isoformat()}
    )
    logger.info("paper account processed %s", counters)
    return counters


def process_all(db: Session, *, through: date | None = None) -> dict:
    """Process every ACTIVE account (daily job entry point). Signal sets are
    ensured once per distinct (strategy, parameters) group."""
    accounts = list(
        db.scalars(
            select(PaperAccount).where(PaperAccount.status == "ACTIVE").order_by(PaperAccount.id)
        )
    )
    seen_groups: set[tuple[int, str]] = set()
    results = []
    for account in accounts:
        group = (account.strategy_id, account.parameter_hash)
        if group not in seen_groups:
            seen_groups.add(group)
            try:
                ensure_signals(db, account)
            except Exception:
                logger.exception("signal ensure failed account=%d", account.id)
        try:
            results.append(process_account(db, account, through=through))
        except Exception as exc:
            db.rollback()
            logger.exception("paper processing failed account=%d", account.id)
            results.append({"account_id": account.id, "error": str(exc)})
    return {"accounts": len(accounts), "results": results}
