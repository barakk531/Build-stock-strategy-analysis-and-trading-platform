"""Portfolio tracker — show current holdings, value, and gains."""

from __future__ import annotations

import argparse
import sys

from portfolio import positions, prices, report, transactions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-f",
        "--file",
        default="transactions.csv",
        help="path to the transaction log (default: transactions.csv)",
    )
    args = parser.parse_args()

    try:
        txns = transactions.load(args.file)
        live, realized = positions.build(txns)
    except (transactions.TransactionError, positions.PositionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not live and not realized:
        print("No transactions yet. Add some to", args.file)
        return 0

    try:
        quotes = prices.latest([p.ticker for p in live])
    except prices.PriceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(report.render(live, realized, quotes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
