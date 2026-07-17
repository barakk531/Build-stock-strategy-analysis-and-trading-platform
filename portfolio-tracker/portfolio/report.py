"""Formatting the portfolio report for the terminal."""

from __future__ import annotations

from .positions import Position, Realized


def _money(x: float) -> str:
    return f"{x:,.2f}"


def _signed(x: float) -> str:
    return f"{x:+,.2f}"


def render(
    positions: list[Position],
    realized: list[Realized],
    quotes: dict[str, float],
) -> str:
    lines: list[str] = []

    header = f"{'TICKER':<8}{'SHARES':>10}{'AVG COST':>12}{'PRICE':>12}{'VALUE':>14}{'GAIN':>14}{'GAIN %':>10}"
    lines.append(header)
    lines.append("-" * len(header))

    total_value = 0.0
    total_basis = 0.0
    stale: list[str] = []

    for p in positions:
        price = quotes.get(p.ticker)
        if price is None:
            stale.append(p.ticker)
            lines.append(
                f"{p.ticker:<8}{p.shares:>10,.4g}{_money(p.avg_cost):>12}{'—':>12}{'—':>14}{'—':>14}{'—':>10}"
            )
            continue

        value = p.shares * price
        gain = value - p.cost_basis
        pct = (gain / p.cost_basis * 100) if p.cost_basis else 0.0

        total_value += value
        total_basis += p.cost_basis

        lines.append(
            f"{p.ticker:<8}{p.shares:>10,.4g}{_money(p.avg_cost):>12}{_money(price):>12}"
            f"{_money(value):>14}{_signed(gain):>14}{pct:>9,.1f}%"
        )

    lines.append("-" * len(header))
    total_gain = total_value - total_basis
    total_pct = (total_gain / total_basis * 100) if total_basis else 0.0
    lines.append(
        f"{'TOTAL':<8}{'':>10}{'':>12}{'':>12}{_money(total_value):>14}"
        f"{_signed(total_gain):>14}{total_pct:>9,.1f}%"
    )

    if realized:
        lines.append("")
        lines.append("Realized")
        for r in realized:
            lines.append(f"  {r.ticker:<8}{_signed(r.gain):>14}  (proceeds {_money(r.proceeds)})")

    if stale:
        lines.append("")
        lines.append(f"No price data for: {', '.join(stale)} — excluded from totals.")

    return "\n".join(lines)
