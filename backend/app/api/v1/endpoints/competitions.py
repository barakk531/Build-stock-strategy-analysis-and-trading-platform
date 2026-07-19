"""Strategy competition API (spec §16): create, list, detail, leaderboard,
membership management. The leaderboard payload also carries the comparison
curves, fairness report, holdings, and best/worst trades for the dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.competition import Competition, CompetitionAccount
from app.models.paper import PaperAccount
from app.schemas.competition import (
    CompetitionCreateIn,
    CompetitionListOut,
    CompetitionOut,
    CompetitionUpdateIn,
)
from app.services.competition import service as competition_service

router = APIRouter(prefix="/competitions")

DbDep = Annotated[Session, Depends(get_db)]


def _get_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail=f"Competition {competition_id} not found")
    return competition


def _out(db: Session, competition: Competition) -> CompetitionOut:
    out = CompetitionOut.model_validate(competition)
    out.account_ids = list(
        db.scalars(
            select(CompetitionAccount.paper_account_id).where(
                CompetitionAccount.competition_id == competition.id
            )
        )
    )
    out.account_count = len(out.account_ids)
    return out


def _validate_accounts(db: Session, account_ids: list[int]) -> None:
    existing = set(
        db.scalars(select(PaperAccount.id).where(PaperAccount.id.in_(account_ids or [0])))
    )
    missing = [i for i in account_ids if i not in existing]
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown paper accounts: {missing}")


@router.post("", response_model=CompetitionOut, status_code=201)
def create_competition(payload: CompetitionCreateIn, db: DbDep) -> CompetitionOut:
    account_ids = list(dict.fromkeys(payload.account_ids))  # dedupe, keep order
    _validate_accounts(db, account_ids)
    competition = Competition(name=payload.name, description=payload.description)
    db.add(competition)
    db.flush()
    for account_id in account_ids:
        db.add(
            CompetitionAccount(competition_id=competition.id, paper_account_id=account_id)
        )
    db.commit()
    db.refresh(competition)
    return _out(db, competition)


@router.get("", response_model=CompetitionListOut)
def list_competitions(db: DbDep) -> CompetitionListOut:
    competitions = list(
        db.scalars(select(Competition).order_by(Competition.created_at.desc()))
    )
    return CompetitionListOut(
        items=[_out(db, c) for c in competitions], total=len(competitions)
    )


@router.get("/{competition_id}", response_model=CompetitionOut)
def get_competition(competition_id: int, db: DbDep) -> CompetitionOut:
    return _out(db, _get_or_404(db, competition_id))


@router.put("/{competition_id}", response_model=CompetitionOut)
def update_competition(
    competition_id: int, payload: CompetitionUpdateIn, db: DbDep
) -> CompetitionOut:
    competition = _get_or_404(db, competition_id)
    if payload.name is not None:
        competition.name = payload.name
    if payload.description is not None:
        competition.description = payload.description
    db.commit()
    return _out(db, competition)


@router.delete("/{competition_id}", status_code=204)
def delete_competition(competition_id: int, db: DbDep) -> Response:
    db.delete(_get_or_404(db, competition_id))  # memberships cascade
    db.commit()
    return Response(status_code=204)


@router.post("/{competition_id}/accounts/{account_id}", response_model=CompetitionOut)
def add_account(competition_id: int, account_id: int, db: DbDep) -> CompetitionOut:
    competition = _get_or_404(db, competition_id)
    _validate_accounts(db, [account_id])
    exists = db.scalar(
        select(CompetitionAccount.id).where(
            CompetitionAccount.competition_id == competition_id,
            CompetitionAccount.paper_account_id == account_id,
        )
    )
    if exists is None:
        db.add(
            CompetitionAccount(competition_id=competition_id, paper_account_id=account_id)
        )
        db.commit()
    return _out(db, competition)


@router.delete("/{competition_id}/accounts/{account_id}", response_model=CompetitionOut)
def remove_account(competition_id: int, account_id: int, db: DbDep) -> CompetitionOut:
    competition = _get_or_404(db, competition_id)
    db.query(CompetitionAccount).filter(
        CompetitionAccount.competition_id == competition_id,
        CompetitionAccount.paper_account_id == account_id,
    ).delete(synchronize_session=False)
    db.commit()
    return _out(db, competition)


@router.get("/{competition_id}/leaderboard")
def get_leaderboard(competition_id: int, db: DbDep) -> dict:
    competition = _get_or_404(db, competition_id)
    return competition_service.leaderboard(db, competition)
