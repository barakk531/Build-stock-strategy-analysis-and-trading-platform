"""SQLAlchemy ORM models.

Importing this package registers every table on Base.metadata — Alembic's
env.py relies on that. Add new model modules to the imports below.
"""

from app.models.daily_price import DailyPrice
from app.models.stock import Stock

__all__ = ["DailyPrice", "Stock"]
