"""Scheduled job functions.

Jobs are plain callables registered by register_jobs; every job must be
idempotent and safe to rerun. Planned jobs (arriving with later phases):

- daily market-data update after the U.S. close    — Phase 2
- weekly S&P 500 universe sync                     — Phase 2
- company metadata / market-cap refresh            — Phase 2
- signal scan + Telegram alert queue               — Phases 3/5
- paper-order execution + equity snapshots         — Phase 7
- data health check                                — Phase 9
"""

from apscheduler.schedulers.base import BaseScheduler


def register_jobs(scheduler: BaseScheduler) -> None:
    """Register all scheduled jobs. No jobs exist yet in Phase 1."""
