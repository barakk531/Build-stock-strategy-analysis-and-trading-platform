"""Strategy registry: stable strategy_type -> engine class."""

from __future__ import annotations

from app.services.strategies.base import Strategy
from app.services.strategies.sma_trend_volume import SmaTrendVolumeStrategy

STRATEGIES: dict[str, type[Strategy]] = {
    SmaTrendVolumeStrategy.strategy_type: SmaTrendVolumeStrategy,
}


def get_strategy(strategy_type: str) -> Strategy:
    try:
        return STRATEGIES[strategy_type]()
    except KeyError as exc:
        raise ValueError(f"Unknown strategy type: {strategy_type}") from exc
