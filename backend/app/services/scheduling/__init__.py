"""Job scheduling runner. Owns APScheduler so it can be swapped for Celery
later without touching job logic (which lives in app.jobs)."""
