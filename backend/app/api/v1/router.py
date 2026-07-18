from fastapi import APIRouter

from app.api.v1.endpoints import admin, health, stocks

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(stocks.router, tags=["stocks"])
api_router.include_router(admin.router, tags=["admin"])
