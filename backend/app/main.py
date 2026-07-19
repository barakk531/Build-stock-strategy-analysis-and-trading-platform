"""Application entry point: app factory, middleware, lifespan, router mount."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.scheduling.scheduler import SchedulerService


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    scheduler = SchedulerService(timezone=settings.market_timezone)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        from app.core.security import warn_if_disabled

        warn_if_disabled()
        if settings.scheduler_enabled:
            scheduler.start()
        yield
        scheduler.shutdown()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
