"""APScheduler lifecycle wrapper.

All triggers must use the market timezone (America/New_York) — never the
server's local date — per the scheduling rules in the project spec.
"""

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.jobs import register_jobs

logger = logging.getLogger(__name__)


class SchedulerService:
    """Starts/stops the background scheduler with the FastAPI lifespan."""

    #: Set by start(); read by GET /admin/jobs. One scheduler per process.
    instance: "SchedulerService | None" = None

    def __init__(self, timezone: str) -> None:
        self._scheduler = BackgroundScheduler(timezone=ZoneInfo(timezone))

    def start(self) -> None:
        register_jobs(self._scheduler)
        self._scheduler.start()
        SchedulerService.instance = self
        logger.info("scheduler started jobs=%d", len(self._scheduler.get_jobs()))

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            SchedulerService.instance = None
            logger.info("scheduler stopped")

    def jobs(self) -> list[dict]:
        return [
            {
                "id": job.id,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]
