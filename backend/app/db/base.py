from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base all ORM models inherit from."""


# Import model modules below so Alembic autogenerate sees every table.
# None yet — the first tables (stocks, daily_prices, ...) arrive in Phase 2.
