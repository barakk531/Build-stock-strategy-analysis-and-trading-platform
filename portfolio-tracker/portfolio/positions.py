"""Deriving current positions and realized gains from a transaction log.

Cost basis uses the average-cost method: every buy re-averages the basis across
all shares held, and a sell realizes gain against that average without changing
it. This is one of several permissible methods (FIFO and specific-lot are the
others) and they produce different realized-gain numbers at tax time.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Position:
    ticker: str
    shares: float
    cost_basis: float  # total dollars in, for the shares still held

    @property
    def avg_cost(self) -> float:
        return self.cost_basis / self.shares if self.shares else 0.0


@dataclass
class Realized:
    ticker: str
    proceeds: float
    basis: float

    @property
    def gain(self) -> float:
        return self.proceeds - self.basis


class PositionError(Exception):
    """Raised when transactions describe an impossible position."""


def build(transactions: pd.DataFrame) -> tuple[list[Position], list[Realized]]:
    """Replay the log chronologically into open positions and realized gains."""
    open_pos: dict[str, Position] = {}
    realized: dict[str, Realized] = {}

    for row in transactions.itertuples():
        pos = open_pos.setdefault(row.ticker, Position(row.ticker, 0.0, 0.0))

        if row.action == "buy":
            pos.shares += row.shares
            pos.cost_basis += row.shares * row.price + row.fees
        else:
            if row.shares > pos.shares + 1e-9:
                raise PositionError(
                    f"{row.date.date()}: selling {row.shares} {row.ticker} "
                    f"but only {pos.shares} held"
                )
            basis_out = pos.avg_cost * row.shares
            pos.cost_basis -= basis_out
            pos.shares -= row.shares

            rec = realized.setdefault(row.ticker, Realized(row.ticker, 0.0, 0.0))
            rec.proceeds += row.shares * row.price - row.fees
            rec.basis += basis_out

    live = [p for p in open_pos.values() if p.shares > 1e-9]
    return sorted(live, key=lambda p: p.ticker), sorted(realized.values(), key=lambda r: r.ticker)
