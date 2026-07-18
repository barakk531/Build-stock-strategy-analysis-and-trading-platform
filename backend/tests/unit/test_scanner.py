"""Scanner state, filter, and sort logic on fabricated snapshot rows."""

from datetime import date

from app.services.scanner import service as scanner


def _row(**overrides):
    base = {
        "symbol": "TST",
        "company_name": "Test Co",
        "sector": "Tech",
        "industry": "Software",
        "market_cap": 10_000_000_000,
        "trade_date": date(2026, 7, 17),
        "close": 100.0,
        "adjusted_close": 100.0,
        "change_pct": 1.0,
        "volume": 2_000_000.0,
        "sma_20": 98.0,
        "sma_50": 95.0,
        "sma_150": 90.0,
        "sma_150_slope": 0.5,
        "average_volume": 1_000_000.0,
        "volume_ratio": 2.0,
        "distance_sma_150_pct": 11.1,
        "buy_state": True,
        "sell_state": False,
        "latest_signal_type": "BUY",
        "latest_signal_date": date(2026, 7, 15),
    }
    base.update(overrides)
    return base


def test_buy_state_requires_all_conditions():
    assert scanner.buy_state(100, 98, 95, 90, 0.0, 1.0) is True  # boundaries inclusive
    assert scanner.buy_state(100, 98, 95, 90, -0.1, 1.0) is False  # falling slope
    assert scanner.buy_state(90, 98, 95, 90, 0.5, 1.0) is False  # price == sma150 strict
    assert scanner.buy_state(100, 95, 95, 90, 0.5, 1.0) is False  # sma20 == sma50 strict
    assert scanner.buy_state(100, 98, 95, 90, 0.5, 0.99) is False  # ratio below 1.0
    assert scanner.buy_state(None, 98, 95, 90, 0.5, 1.0) is False  # missing data


def test_sell_state_both_conditions_strict():
    assert scanner.sell_state(80, 90, 95, 90) is True
    assert scanner.sell_state(90, 90, 95, 90) is False  # price == sma150
    assert scanner.sell_state(80, 95, 95, 90) is False  # sma20 == sma50
    assert scanner.sell_state(80, 90, 95, None) is False


def test_filters_search_sector_states_and_ranges():
    rows = [
        _row(symbol="AAA", sector="Tech", buy_state=True, volume_ratio=2.0),
        _row(symbol="BBB", company_name="Banana Corp", sector="Energy",
             buy_state=False, sell_state=True, volume_ratio=0.5),
        _row(symbol="CCC", sector="Tech", buy_state=False, market_cap=1_000_000_000),
    ]
    assert [r["symbol"] for r in scanner.apply_filters(rows, search="banana")] == ["BBB"]
    assert [r["symbol"] for r in scanner.apply_filters(rows, sector="Tech")] == ["AAA", "CCC"]
    assert [r["symbol"] for r in scanner.apply_filters(rows, buy_state_only=True)] == ["AAA"]
    assert [r["symbol"] for r in scanner.apply_filters(rows, sell_state_only=True)] == ["BBB"]
    high_ratio = scanner.apply_filters(rows, min_volume_ratio=1.0)
    assert [r["symbol"] for r in high_ratio] == ["AAA", "CCC"]
    assert [r["symbol"] for r in scanner.apply_filters(rows, min_market_cap=5_000_000_000)] == [
        "AAA", "BBB",
    ]


def test_filter_price_vs_sma150_and_slope():
    rows = [
        _row(symbol="UP", adjusted_close=100, sma_150=90, sma_150_slope=1.0),
        _row(symbol="DN", adjusted_close=80, sma_150=90, sma_150_slope=-1.0),
        _row(symbol="FLAT", adjusted_close=91, sma_150=90, sma_150_slope=0.01),
        _row(symbol="NA", adjusted_close=None, sma_150=None, sma_150_slope=None),
    ]
    assert [r["symbol"] for r in scanner.apply_filters(rows, price_vs_sma150="above")] == [
        "UP", "FLAT",
    ]
    assert [r["symbol"] for r in scanner.apply_filters(rows, price_vs_sma150="below")] == ["DN"]
    assert [r["symbol"] for r in scanner.apply_filters(rows, slope="positive")] == ["UP", "FLAT"]
    assert [r["symbol"] for r in scanner.apply_filters(rows, slope="negative")] == ["DN"]
    assert [r["symbol"] for r in scanner.apply_filters(rows, slope="flat")] == ["FLAT"]


def test_sort_rows_orders_and_puts_missing_last():
    rows = [
        _row(symbol="A", volume_ratio=1.0),
        _row(symbol="B", volume_ratio=None),
        _row(symbol="C", volume_ratio=3.0),
    ]
    ordered = scanner.sort_rows(rows, sort="volume_ratio", order="desc")
    assert [r["symbol"] for r in ordered] == ["C", "A", "B"]
    ordered = scanner.sort_rows(rows, sort="volume_ratio", order="asc")
    assert [r["symbol"] for r in ordered] == ["A", "C", "B"]


def test_sort_unknown_key_falls_back_to_symbol():
    rows = [_row(symbol="B"), _row(symbol="A")]
    assert [r["symbol"] for r in scanner.sort_rows(rows, sort="nope")] == ["A", "B"]
