"""Liveness endpoint reporting API status and database reachability.

Returns 200 with status="degraded" (rather than a 5xx) when the database is
down, so the frontend and container healthchecks can distinguish "API dead"
from "API up, DB unreachable".
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db import session
from app.schemas.health import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    settings = get_settings()

    database = "ok"
    try:
        # session.engine (not a from-import) so tests can monkeypatch the module attribute.
        with session.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("health db_check=failed error=%s", exc.__class__.__name__)
        database = "unavailable"

    from app.core.security import auth_required

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=settings.app_version,
        environment=settings.environment,
        database=database,
        auth_required=auth_required(),
        timestamp=datetime.now(UTC),
    )
