"""Backtest API: create/launch runs, poll status, read results.

POST launches the run in the background and returns immediately — the
frontend polls GET /backtests/{id} until status leaves RUNNING. `sync=true`
executes in-request (small runs, tests, scripts)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.backtest import BacktestRun
from app.repositories import backtest_repository
from app.schemas.backtest import (
    BacktestCreateIn,
    BacktestDetailOut,
    BacktestListOut,
    BacktestSkipListOut,
    BacktestSummaryOut,
    BacktestTradeListOut,
)
from app.services.backtesting import runner

router = APIRouter(prefix="/backtests")

DbDep = Annotated[Session, Depends(get_db)]


def _summary(run: BacktestRun) -> BacktestSummaryOut:
    out = BacktestSummaryOut.model_validate(run)
    metrics = (run.results_json or {}).get("metrics") or {}
    out.total_return_pct = metrics.get("total_return_pct")
    out.max_drawdown_pct = metrics.get("max_drawdown_pct")
    out.trades_count = metrics.get("trades")
    return out


def _get_or_404(db: Session, run_id: int) -> BacktestRun:
    run = backtest_repository.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Backtest {run_id} not found")
    return run


@router.post("", response_model=BacktestSummaryOut, status_code=201)
def create_backtest(
    payload: BacktestCreateIn,
    background: BackgroundTasks,
    db: DbDep,
    sync: Annotated[bool, Query(description="Execute in-request instead of background")] = False,
) -> BacktestSummaryOut:
    from sqlalchemy import func, select

    from app.core.config import get_settings

    # Guardrail, not a scheduler: full-universe runs hold large frames, so
    # unbounded concurrent launches could exhaust memory.
    active = db.scalar(
        select(func.count()).where(BacktestRun.status.in_(["PENDING", "RUNNING"]))
    ) or 0
    limit = get_settings().max_concurrent_backtests
    if active >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"{active} backtests already queued/running (limit {limit}) — "
            "wait for one to finish or delete a stuck run.",
        )
    try:
        run = runner.create_run(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if sync:
        run = runner.execute_run(db, run.id)
    else:
        background.add_task(runner.execute_run_in_background, run.id)
    return _summary(run)


@router.get("", response_model=BacktestListOut)
def list_backtests(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BacktestListOut:
    runs, total = backtest_repository.list_runs(db, limit=limit, offset=offset)
    return BacktestListOut(
        items=[_summary(run) for run in runs], total=total, limit=limit, offset=offset
    )


@router.get("/{run_id}", response_model=BacktestDetailOut)
def get_backtest(run_id: int, db: DbDep) -> BacktestDetailOut:
    return BacktestDetailOut.model_validate(_get_or_404(db, run_id))


@router.delete("/{run_id}", status_code=204)
def delete_backtest(run_id: int, db: DbDep) -> Response:
    run = _get_or_404(db, run_id)
    if run.status == "RUNNING":
        raise HTTPException(status_code=409, detail="Backtest is still running")
    backtest_repository.delete_run(db, run)
    return Response(status_code=204)


@router.get("/{run_id}/trades", response_model=BacktestTradeListOut)
def list_backtest_trades(
    run_id: int,
    db: DbDep,
    status: Annotated[str | None, Query(pattern="^(?i)(open|closed)$")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BacktestTradeListOut:
    _get_or_404(db, run_id)
    rows, total = backtest_repository.list_trades(
        db, run_id, status=status, limit=limit, offset=offset
    )
    return BacktestTradeListOut(items=rows, total=total, limit=limit, offset=offset)


@router.get("/{run_id}/skips", response_model=BacktestSkipListOut)
def list_backtest_skips(
    run_id: int,
    db: DbDep,
    reason: Annotated[str | None, Query(max_length=30)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BacktestSkipListOut:
    _get_or_404(db, run_id)
    rows, total = backtest_repository.list_skips(
        db, run_id, reason=reason, limit=limit, offset=offset
    )
    return BacktestSkipListOut(items=rows, total=total, limit=limit, offset=offset)
