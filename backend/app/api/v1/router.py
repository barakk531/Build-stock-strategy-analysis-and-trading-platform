from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    backtests,
    health,
    paper_accounts,
    scanner,
    signals,
    stocks,
    strategies,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(stocks.router, tags=["stocks"])
api_router.include_router(scanner.router, tags=["scanner"])
api_router.include_router(signals.router, tags=["signals"])
api_router.include_router(strategies.router, tags=["strategies"])
api_router.include_router(backtests.router, tags=["backtests"])
api_router.include_router(paper_accounts.router, tags=["paper-accounts"])
api_router.include_router(admin.router, tags=["admin"])
