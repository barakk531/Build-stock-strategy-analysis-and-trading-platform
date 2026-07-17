# Architecture

## Overview

Monorepo with three services orchestrated by Docker Compose:

```
frontend (React SPA, :5173)  ──/api proxy──▶  backend (FastAPI, :8000)  ──▶  db (PostgreSQL 16, :5432)
```

## Backend

Layered; requests flow one direction and business logic never lives in route
handlers:

```
app/api/v1        thin routers + endpoint modules (HTTP concerns only)
app/schemas       Pydantic models at the API boundary
app/services      business logic, one subpackage per domain
app/repositories  all data access / queries
app/models        SQLAlchemy ORM models (tables arrive in Phase 2)
app/db            engine, session factory, declarative base
app/core          settings (pydantic-settings), logging
app/jobs          scheduled job functions (idempotent)
```

Decisions:

- **Sync SQLAlchemy 2** (psycopg 3) with plain `def` endpoints running on
  FastAPI's threadpool. The workload is pandas-heavy and job-driven; async
  buys nothing here and complicates Alembic and APScheduler integration.
- **Settings** come from environment variables first, then the repo-root
  `.env`. Docker Compose injects container-specific values (e.g.
  `DATABASE_URL` pointing at the `db` service) as env vars.
- **Scheduling** uses APScheduler, isolated behind
  `app/services/scheduling/SchedulerService`; job functions live in
  `app/jobs`. Swapping to Celery later replaces only the runner. All triggers
  use `America/New_York` — never the server's local date.
- **Migrations**: Alembic, wired to app settings and `Base.metadata`.
  Every schema change goes through a migration.

## Frontend

React (JavaScript) + Vite. Server state is owned by TanStack Query; the small
amount of global UI state lives in a Zustand store. Styling is Tailwind CSS v4.
Charts (Phase 4) use TradingView Lightweight Charts — purpose-built for
candlesticks, SMA overlays, a volume pane, and buy/sell markers over 20 years
of daily bars.

In dev the browser talks only to Vite (`:5173`); `/api/*` is proxied to the
backend, so CORS never bites. CORS middleware is still configured for direct
access.

## Phase map

| Phase | Delivers |
| ----- | -------- |
| 1 | This foundation: services boot, health endpoint, migrations, tests |
| 2 | S&P 500 universe sync, 20y Yahoo history, incremental refresh |
| 3 | Indicators (SMA 20/50/150, volume avg, slope), strategy engine, signals |
| 4 | Scanner + individual stock page with charts |
| 5 | Telegram alerts |
| 6 | Backtesting |
| 7 | Paper accounts |
| 8 | Strategy competition |
| 9 | Auth, admin hardening, deployment |
