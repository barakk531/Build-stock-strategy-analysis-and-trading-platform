"""Market scanner endpoint: filter + sort the merged per-stock snapshot."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.scanner import ScannerOut
from app.services.scanner import service as scanner

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/scanner", response_model=ScannerOut)
def get_scanner(
    db: DbDep,
    search: Annotated[str | None, Query(max_length=60)] = None,
    sector: str | None = None,
    buy_state: bool = False,
    sell_state: bool = False,
    signal_type: Annotated[str | None, Query(pattern="^(?i)(buy|sell)$")] = None,
    price_vs_sma150: Literal["above", "below"] | None = None,
    sma20_vs_sma50: Literal["above", "below"] | None = None,
    slope: Literal["positive", "negative", "flat"] | None = None,
    min_volume_ratio: Annotated[float | None, Query(ge=0)] = None,
    min_market_cap: Annotated[int | None, Query(ge=0)] = None,
    max_market_cap: Annotated[int | None, Query(ge=0)] = None,
    sort: str = "symbol",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=520)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScannerOut:
    snapshot = scanner.build_snapshot(db)
    sectors = sorted({row["sector"] for row in snapshot if row["sector"]})
    rows = scanner.apply_filters(
        snapshot,
        search=search,
        sector=sector,
        buy_state_only=buy_state,
        sell_state_only=sell_state,
        signal_type=signal_type,
        price_vs_sma150=price_vs_sma150,
        sma20_vs_sma50=sma20_vs_sma50,
        slope=slope,
        min_volume_ratio=min_volume_ratio,
        min_market_cap=min_market_cap,
        max_market_cap=max_market_cap,
    )
    rows = scanner.sort_rows(rows, sort=sort, order=order)
    return ScannerOut(
        items=rows[offset : offset + limit],
        total=len(rows),
        limit=limit,
        offset=offset,
        sectors=sectors,
    )
