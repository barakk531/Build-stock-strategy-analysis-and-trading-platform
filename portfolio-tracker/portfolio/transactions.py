"""Loading and validating the transaction log."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

COLUMNS = ["date", "ticker", "action", "shares", "price", "fees"]
ACTIONS = {"buy", "sell"}


class TransactionError(Exception):
    """Raised when the transaction log is malformed."""


def load(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise TransactionError(f"No transaction file at {path}")

    df = pd.read_csv(path)

    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise TransactionError(f"{path} is missing columns: {', '.join(missing)}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        bad = df.index[df["date"].isna()].tolist()
        raise TransactionError(f"Unparseable dates on row(s): {bad}")

    df["ticker"] = df["ticker"].str.strip().str.upper()
    df["action"] = df["action"].str.strip().str.lower()

    unknown = set(df["action"]) - ACTIONS
    if unknown:
        raise TransactionError(f"Unknown action(s): {', '.join(sorted(unknown))}")

    for col in ("shares", "price", "fees"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            raise TransactionError(f"Non-numeric values in '{col}'")

    if (df["shares"] <= 0).any():
        raise TransactionError("Share counts must be positive; use action=sell to reduce a position")

    return df.sort_values("date").reset_index(drop=True)
