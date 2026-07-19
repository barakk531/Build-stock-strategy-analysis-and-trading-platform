from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (
    admin,
    backtests,
    competitions,
    health,
    paper_accounts,
    scanner,
    signals,
    stocks,
    strategies,
)
from app.core.security import require_admin

api_router = APIRouter()

# Public read-only market data and analysis.
api_router.include_router(health.router, tags=["health"])
api_router.include_router(stocks.router, tags=["stocks"])
api_router.include_router(scanner.router, tags=["scanner"])
api_router.include_router(signals.router, tags=["signals"])
api_router.include_router(strategies.router, tags=["strategies"])

# Trading state + administration: API-key protected when ADMIN_API_KEY is set
# (spec §20). With no key configured the dependency is a no-op (local dev).
_guarded = [Depends(require_admin)]
api_router.include_router(backtests.router, tags=["backtests"], dependencies=_guarded)
api_router.include_router(paper_accounts.router, tags=["paper-accounts"], dependencies=_guarded)
api_router.include_router(competitions.router, tags=["competitions"], dependencies=_guarded)
api_router.include_router(admin.router, tags=["admin"], dependencies=_guarded)
