"""Downloader frame cleaning: NaN/zero/negative handling, adjusted-close fallback."""

import math

import pandas as pd

from app.services.market_data import downloader


def _frame(rows: dict) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(frame.pop("date"))
    return frame


def test_frame_to_rows_happy_path():
    frame = _frame(
        {
            "date": ["2026-07-16", "2026-07-17"],
            "Open": [100.0, 101.5],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.5],
            "Adj Close": [100.5, 102.0],
            "Volume": [1_000_000, 2_000_000],
            "Dividends": [0.0, 0.25],
            "Stock Splits": [0.0, 0.0],
        }
    )
    rows = downloader.frame_to_rows(frame)
    assert len(rows) == 2
    assert str(rows[0]["trade_date"]) == "2026-07-16"
    assert rows[0]["close"] == 101.0
    assert rows[0]["adjusted_close"] == 100.5
    assert rows[1]["dividend"] == 0.25
    assert rows[1]["volume"] == 2_000_000


def test_frame_to_rows_skips_nan_close_rows():
    frame = _frame(
        {
            "date": ["2026-07-16", "2026-07-17"],
            "Open": [100.0, float("nan")],
            "High": [102.0, float("nan")],
            "Low": [99.0, float("nan")],
            "Close": [101.0, float("nan")],
            "Adj Close": [100.5, float("nan")],
            "Volume": [1_000_000, float("nan")],
            "Dividends": [0.0, 0.0],
            "Stock Splits": [0.0, 0.0],
        }
    )
    rows = downloader.frame_to_rows(frame)
    assert len(rows) == 1


def test_frame_to_rows_rejects_nonpositive_close_and_negative_volume():
    frame = _frame(
        {
            "date": ["2026-07-15", "2026-07-16", "2026-07-17"],
            "Close": [0.0, -5.0, 50.0],
            "Adj Close": [0.0, -5.0, 49.5],
            "Volume": [10, 10, -1],
        }
    )
    rows = downloader.frame_to_rows(frame)
    assert rows == []  # zero close, negative close, negative volume all dropped


def test_frame_to_rows_falls_back_to_close_when_adj_missing():
    frame = _frame(
        {
            "date": ["2026-07-17"],
            "Close": [50.0],
            "Adj Close": [float("nan")],
            "Volume": [100],
        }
    )
    rows = downloader.frame_to_rows(frame)
    assert rows[0]["adjusted_close"] == 50.0


def test_frame_to_rows_missing_volume_becomes_none():
    frame = _frame({"date": ["2026-07-17"], "Close": [50.0], "Adj Close": [49.0]})
    rows = downloader.frame_to_rows(frame)
    assert rows[0]["volume"] is None


def test_clean_number_handles_inf_and_nan():
    assert downloader._clean_number(float("inf")) is None
    assert downloader._clean_number(float("nan")) is None
    assert downloader._clean_number("3.5") == 3.5
    assert downloader._clean_number("abc") is None
    assert not math.isnan(downloader._clean_number(0.0))
