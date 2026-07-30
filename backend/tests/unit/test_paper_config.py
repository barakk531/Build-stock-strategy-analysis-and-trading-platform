"""AccountSettings validation — mirrors BacktestConfig's symbol guard so a
malformed benchmark can never reach ensure_stock's INSERT."""

import pytest
from pydantic import ValidationError

from app.services.paper_trading.config import AccountSettings


def test_overlong_benchmark_symbol_rejected():
    with pytest.raises(ValidationError, match="benchmark symbol"):
        AccountSettings(benchmark_symbol="X" * 25)


def test_invalid_benchmark_characters_rejected():
    with pytest.raises(ValidationError, match="benchmark symbol"):
        AccountSettings(benchmark_symbol="AAPL OR 1=1")


def test_valid_symbols_pass_through_uppercased():
    settings = AccountSettings(benchmark_symbol="^gspc")
    assert settings.benchmark_symbol == "^GSPC"


def test_empty_benchmark_becomes_none():
    assert AccountSettings(benchmark_symbol="").benchmark_symbol is None


def test_market_cap_bounds_ordered():
    with pytest.raises(ValidationError, match="minimum_market_cap"):
        AccountSettings(minimum_market_cap=100, maximum_market_cap=50)
