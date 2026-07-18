"""SQLAlchemy ORM models.

Importing this package registers every table on Base.metadata — Alembic's
env.py relies on that. Add new model modules to the imports below.
"""

from app.models.daily_indicator import DailyIndicator
from app.models.daily_price import DailyPrice
from app.models.signal import Signal
from app.models.stock import Stock
from app.models.strategy import Strategy

__all__ = ["DailyIndicator", "DailyPrice", "Signal", "Stock", "Strategy"]
