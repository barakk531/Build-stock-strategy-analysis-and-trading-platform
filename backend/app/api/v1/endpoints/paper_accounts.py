"""Paper-account API (spec §16): CRUD, pause/resume, positions, orders,
performance. Creation launches the initial catch-up replay in the background;
POST /{id}/process (and the daily job) advance accounts afterwards."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.paper import PaperAccount, PaperOrder, PaperPosition
from app.schemas.paper import (
    AccountCreateIn,
    AccountDetailOut,
    AccountListOut,
    AccountOut,
    AccountUpdateIn,
    OrderListOut,
    PositionListOut,
    PositionOut,
)
from app.services.paper_trading import processor
from app.services.paper_trading import service as paper_service

router = APIRouter(prefix="/paper-accounts")

DbDep = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, account_id: int) -> PaperAccount:
    account = db.get(PaperAccount, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"Paper account {account_id} not found")
    return account


def _enrich(db: Session, account: PaperAccount, out_model=AccountOut):
    out = out_model.model_validate(account)
    for key, value in paper_service.summarize(db, account).items():
        setattr(out, key, value)
    return out


def _process_in_background(account_id: int) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        account = db.get(PaperAccount, account_id)
        if account is not None:
            processor.ensure_signals(db, account)
            processor.process_account(db, account)
    finally:
        db.close()


@router.post("", response_model=AccountOut, status_code=201)
def create_account(
    payload: AccountCreateIn,
    background: BackgroundTasks,
    db: DbDep,
    sync: Annotated[bool, Query(description="Run the initial catch-up in-request")] = False,
) -> AccountOut:
    try:
        account = paper_service.create_account(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if sync:
        processor.ensure_signals(db, account)
        processor.process_account(db, account)
    else:
        background.add_task(_process_in_background, account.id)
    return _enrich(db, account)


@router.get("", response_model=AccountListOut)
def list_accounts(db: DbDep) -> AccountListOut:
    accounts = list(db.scalars(select(PaperAccount).order_by(PaperAccount.id)))
    return AccountListOut(items=[_enrich(db, a) for a in accounts], total=len(accounts))


@router.get("/{account_id}", response_model=AccountDetailOut)
def get_account(account_id: int, db: DbDep) -> AccountDetailOut:
    return _enrich(db, _get_or_404(db, account_id), AccountDetailOut)


@router.put("/{account_id}", response_model=AccountDetailOut)
def update_account(account_id: int, payload: AccountUpdateIn, db: DbDep) -> AccountDetailOut:
    account = _get_or_404(db, account_id)
    if payload.name is not None:
        account.name = payload.name
    if payload.settings is not None:
        has_orders = db.scalar(
            select(func.count()).where(PaperOrder.paper_account_id == account.id)
        )
        if has_orders:
            raise HTTPException(
                status_code=409,
                detail="Settings are frozen once the account has orders — "
                "create a new account to trade a different configuration.",
            )
        account.settings_json = payload.settings.model_dump(mode="json")
    db.commit()
    db.refresh(account)
    return _enrich(db, account, AccountDetailOut)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: DbDep) -> Response:
    account = _get_or_404(db, account_id)
    db.delete(account)  # positions/orders/snapshots cascade
    db.commit()
    return Response(status_code=204)


@router.post("/{account_id}/pause", response_model=AccountOut)
def pause_account(account_id: int, db: DbDep) -> AccountOut:
    account = _get_or_404(db, account_id)
    if account.status == "ACTIVE":
        account.status = "PAUSED"
        db.commit()
    return _enrich(db, account)


@router.post("/{account_id}/resume", response_model=AccountOut)
def resume_account(account_id: int, db: DbDep) -> AccountOut:
    account = _get_or_404(db, account_id)
    if account.status == "PAUSED":
        account.status = "ACTIVE"
        db.commit()
    return _enrich(db, account)


@router.post("/{account_id}/process")
def process_account_now(account_id: int, db: DbDep) -> dict:
    """Manually advance this account through the latest stored trading day."""
    account = _get_or_404(db, account_id)
    processor.ensure_signals(db, account)
    return processor.process_account(db, account)


@router.get("/{account_id}/positions", response_model=PositionListOut)
def list_positions(
    account_id: int,
    db: DbDep,
    status: Annotated[str | None, Query(pattern="^(?i)(open|closed)$")] = None,
) -> PositionListOut:
    account = _get_or_404(db, account_id)
    if status is None or status.upper() == "OPEN":
        marked = paper_service.open_positions_with_marks(db, account)
        open_rows = [PositionOut(**row) for row in marked]
        if status is not None:
            return PositionListOut(items=open_rows, total=len(open_rows))
    else:
        open_rows = []
    closed_rows = list(
        db.scalars(
            select(PaperPosition)
            .where(
                PaperPosition.paper_account_id == account_id,
                PaperPosition.status == "CLOSED",
            )
            .order_by(PaperPosition.closed_at.desc(), PaperPosition.symbol)
        )
    )
    items = open_rows + [PositionOut.model_validate(p) for p in closed_rows]
    return PositionListOut(items=items, total=len(items))


@router.get("/{account_id}/orders", response_model=OrderListOut)
def list_orders(
    account_id: int,
    db: DbDep,
    status: Annotated[str | None, Query(max_length=9)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderListOut:
    _get_or_404(db, account_id)
    query = select(PaperOrder).where(PaperOrder.paper_account_id == account_id)
    if status:
        query = query.where(PaperOrder.status == status.upper())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(PaperOrder.signal_date.desc(), PaperOrder.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return OrderListOut(items=rows, total=total, limit=limit, offset=offset)


@router.get("/{account_id}/performance")
def account_performance(account_id: int, db: DbDep) -> dict:
    account = _get_or_404(db, account_id)
    return paper_service.performance(db, account)
