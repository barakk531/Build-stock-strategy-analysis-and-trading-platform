import pandas as pd
import pytest

from portfolio.positions import PositionError, build


def txns(*rows):
    return pd.DataFrame(
        [dict(zip(["date", "ticker", "action", "shares", "price", "fees"], r)) for r in rows]
    ).assign(date=lambda d: pd.to_datetime(d["date"]))


def test_buys_average_the_cost_basis():
    live, _ = build(
        txns(
            ("2024-01-01", "AAPL", "buy", 10, 100.0, 0),
            ("2024-06-01", "AAPL", "buy", 10, 200.0, 0),
        )
    )
    assert live[0].shares == 20
    assert live[0].avg_cost == pytest.approx(150.0)


def test_fees_are_added_to_basis():
    live, _ = build(txns(("2024-01-01", "AAPL", "buy", 10, 100.0, 9.99)))
    assert live[0].cost_basis == pytest.approx(1009.99)


def test_sell_realizes_gain_and_leaves_avg_cost_unchanged():
    live, realized = build(
        txns(
            ("2024-01-01", "AAPL", "buy", 10, 100.0, 0),
            ("2024-06-01", "AAPL", "sell", 4, 150.0, 0),
        )
    )
    assert realized[0].gain == pytest.approx(200.0)  # 4 * (150 - 100)
    assert live[0].shares == 6
    assert live[0].avg_cost == pytest.approx(100.0)


def test_fees_reduce_proceeds_on_sale():
    _, realized = build(
        txns(
            ("2024-01-01", "AAPL", "buy", 10, 100.0, 0),
            ("2024-06-01", "AAPL", "sell", 10, 110.0, 50.0),
        )
    )
    assert realized[0].gain == pytest.approx(50.0)  # 1100 - 50 - 1000


def test_fully_closed_position_drops_out_but_keeps_realized_gain():
    live, realized = build(
        txns(
            ("2024-01-01", "AAPL", "buy", 5, 100.0, 0),
            ("2024-06-01", "AAPL", "sell", 5, 120.0, 0),
        )
    )
    assert live == []
    assert realized[0].gain == pytest.approx(100.0)


def test_overselling_is_rejected():
    with pytest.raises(PositionError, match="only"):
        build(
            txns(
                ("2024-01-01", "AAPL", "buy", 5, 100.0, 0),
                ("2024-06-01", "AAPL", "sell", 6, 120.0, 0),
            )
        )
