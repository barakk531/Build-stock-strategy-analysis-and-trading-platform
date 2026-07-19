"""Scheduled job functions (spec §18).

Jobs are plain callables owning their own database session; every job is
idempotent and safe to rerun (upserts, dedupe constraints, replay-from-last
processing). Times are America/New_York via the scheduler's timezone.

- daily_market_update  — weekdays 18:30 ET, after the close and Yahoo's EOD
  settle: price sync → indicator recalc → signal scan → Telegram queue+send →
  paper-account processing + equity snapshots. The 5-day resync overlap heals
  late revisions.
- weekly_universe_sync — Saturday 09:00 ET: S&P 500 membership (removals are
  deactivated, never deleted; manual/benchmark rows untouched).
- metadata_refresh     — daily 19:45 ET: market cap / company info, oldest
  first, capped per run so the universe cycles over a few days.
- health_check         — daily 20:15 ET: log-level report of stale prices,
  pending alerts/orders stuck too long.
"""

from zoneinfo import ZoneInfo

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.jobs import pipeline


def register_jobs(scheduler: BaseScheduler) -> None:
    # CronTrigger resolves its timezone at CONSTRUCTION (the scheduler default
    # does not apply), so the market zone must be passed explicitly — never
    # the server's local time (spec §3/§18).
    tz = ZoneInfo(get_settings().market_timezone)
    scheduler.add_job(
        pipeline.daily_market_update,
        CronTrigger(day_of_week="mon-fri", hour=18, minute=30, timezone=tz),
        id="daily_market_update",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600 * 4,
    )
    scheduler.add_job(
        pipeline.weekly_universe_sync,
        CronTrigger(day_of_week="sat", hour=9, minute=0, timezone=tz),
        id="weekly_universe_sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600 * 12,
    )
    scheduler.add_job(
        pipeline.metadata_refresh,
        CronTrigger(day_of_week="mon-sat", hour=19, minute=45, timezone=tz),
        id="metadata_refresh",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600 * 4,
    )
    scheduler.add_job(
        pipeline.health_check,
        CronTrigger(hour=20, minute=15, timezone=tz),
        id="health_check",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600 * 4,
    )
