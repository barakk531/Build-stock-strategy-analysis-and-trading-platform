"""SQLAlchemy ORM models.

Importing this package registers every table on Base.metadata — Alembic's
env.py relies on that. Add new model modules to the imports below.
"""

from app.models.backtest import BacktestRun, BacktestSkip, BacktestTrade
from app.models.daily_indicator import DailyIndicator
from app.models.daily_price import DailyPrice
from app.models.paper import AccountEquitySnapshot, PaperAccount, PaperOrder, PaperPosition
from app.models.signal import Signal
from app.models.stock import Stock
from app.models.strategy import Strategy
from app.models.telegram_alert import TelegramAlert

__all__ = [
    "AccountEquitySnapshot",
    "BacktestRun",
    "BacktestSkip",
    "BacktestTrade",
    "DailyIndicator",
    "DailyPrice",
    "PaperAccount",
    "PaperOrder",
    "PaperPosition",
    "Signal",
    "Stock",
    "Strategy",
    "TelegramAlert",
]
