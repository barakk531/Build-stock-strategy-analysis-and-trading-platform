"""Preset rule_composer strategies so users never start from a blank page.

Each preset is a valid RuleComposerParams config a user can clone (via the
existing competition.clone_account flow) and tweak. Every preset is validated
through the engine at seed time, so a malformed preset fails fast rather than
reaching the database. Presets are stored as ordinary strategy rows
(strategy_type "rule_composer"), deduplicated by (name, version).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.strategy import Strategy as StrategyModel
from app.services.strategies.rule_composer import RuleComposerStrategy

logger = logging.getLogger(__name__)


def _price():
    return {"type": "price"}


def _ind(name, field=None, **params):
    op = {"type": "indicator", "name": name, "params": params}
    if field:
        op["field"] = field
    return op


def _const(value):
    return {"type": "const", "value": value}


def _cond(left, comparison, right, key=None):
    out = {"left": left, "comparison": comparison, "right": right}
    if key:
        out["key"] = key
    return out


PRESETS: list[dict] = [
    {
        "name": "Trend Following (SMA + Volume)",
        "description": (
            "Buys confirmed uptrends: price above SMA 150 with a flat-or-rising "
            "150-day slope, SMA 20 above SMA 50, on above-average volume. Exits "
            "when price and the short SMA break down. Mirrors the platform's "
            "original SMA Trend and Volume rules."
        ),
        "parameters": {
            "entry": {
                "combine": "all",
                "conditions": [
                    _cond(_price(), ">", _ind("sma", period=150), "price_above_sma_long"),
                    _cond(
                        _ind("sma", period=20), ">", _ind("sma", period=50), "short_above_medium"
                    ),
                    _cond(_ind("ma_slope", period=150, lookback=10), ">=", _const(0), "slope_up"),
                    _cond(_ind("volume"), ">=", _ind("avg_volume", period=10), "volume_above_avg"),
                ],
            },
            "exit": {
                "combine": "all",
                "conditions": [
                    _cond(_price(), "<", _ind("sma", period=150), "price_below_sma_long"),
                    _cond(
                        _ind("sma", period=20), "<", _ind("sma", period=50), "short_below_medium"
                    ),
                ],
            },
        },
    },
    {
        "name": "Mean Reversion (RSI + Bollinger)",
        "description": (
            "Buys oversold dips inside an uptrend: RSI below 35 and price below "
            "the lower Bollinger band while price is above SMA 200. Exits as the "
            "bounce matures (RSI back above 55 or price back above the band middle)."
        ),
        "parameters": {
            "entry": {
                "combine": "all",
                "conditions": [
                    _cond(_ind("rsi", period=14), "<", _const(35), "rsi_oversold"),
                    _cond(
                        _price(),
                        "<",
                        _ind("bollinger", "lower", period=20, k=2.0),
                        "below_lower_band",
                    ),
                    _cond(_price(), ">", _ind("sma", period=200), "uptrend_filter"),
                ],
            },
            "exit": {
                "combine": "any",
                "conditions": [
                    _cond(_ind("rsi", period=14), ">", _const(55), "rsi_recovered"),
                    _cond(
                        _price(),
                        ">",
                        _ind("bollinger", "mid", period=20, k=2.0),
                        "back_to_mean",
                    ),
                ],
            },
        },
    },
    {
        "name": "Breakout (Donchian + ADX)",
        "description": (
            "Buys strength: price breaks above the prior 20-day high with a "
            "trending ADX (>= 20). Exits when price falls back below the prior "
            "10-day low (a Donchian channel stop)."
        ),
        "parameters": {
            "entry": {
                "combine": "all",
                "conditions": [
                    _cond(_price(), ">", _ind("donchian", "high", period=20), "breakout_high"),
                    _cond(_ind("adx", period=14), ">=", _const(20), "trending"),
                ],
            },
            "exit": {
                "combine": "any",
                "conditions": [
                    _cond(_price(), "<", _ind("donchian", "low", period=10), "breakdown_low"),
                ],
            },
        },
    },
    {
        "name": "Momentum (6-month + Trend)",
        "description": (
            "Buys leaders: positive 6-month (126-day) return while price is above "
            "SMA 100. Exits when price loses the SMA 100."
        ),
        "parameters": {
            "entry": {
                "combine": "all",
                "conditions": [
                    _cond(_ind("return_n", period=126), ">", _const(0), "positive_6m"),
                    _cond(_price(), ">", _ind("sma", period=100), "above_trend"),
                ],
            },
            "exit": {
                "combine": "any",
                "conditions": [
                    _cond(_price(), "<", _ind("sma", period=100), "lost_trend"),
                ],
            },
        },
    },
]


def seed_presets(db: Session) -> list[StrategyModel]:
    """Get-or-create every preset strategy row. Idempotent."""
    engine = RuleComposerStrategy()
    rows: list[StrategyModel] = []
    for preset in PRESETS:
        existing = db.scalar(
            select(StrategyModel).where(
                StrategyModel.name == preset["name"], StrategyModel.version == engine.version
            )
        )
        if existing:
            rows.append(existing)
            continue
        params = engine.validate_parameters(preset["parameters"])  # fail fast on a bad preset
        row = StrategyModel(
            name=preset["name"],
            description=preset["description"],
            strategy_type=engine.strategy_type,
            version=engine.version,
            parameters_json=engine.parameter_snapshot(params),
            is_active=True,
        )
        db.add(row)
        rows.append(row)
        logger.info("seeded preset strategy %s", preset["name"])
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows
