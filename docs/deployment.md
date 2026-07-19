# Deployment, backups, and production configuration

This platform is designed for a single operator. "Production" means: running
unattended on a machine you control, protected by an API key, with backups.
It is **not** hardened for untrusted multi-user internet exposure.

## Production configuration checklist (spec §20)

1. **Set `ADMIN_API_KEY`** to a long random value (e.g. `openssl rand -hex 32`).
   Without it, admin and trading-state endpoints are unprotected (the server
   logs a warning and `/api/v1/health` reports `auth_required: false`).
   The frontend stores the key locally (Settings page) and sends it as the
   `X-API-Key` header.
2. **Secrets live only in environment variables** (`.env`, never committed):
   `POSTGRES_PASSWORD`, `ADMIN_API_KEY`, `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`. The API masks them everywhere it reports config.
3. **Database is loopback-only** in both compose files
   (`127.0.0.1:5432:5432`). Do not change this unless you add TLS + auth in
   front of Postgres.
4. **Run the production compose** (no code mounts, no reload, restart
   policies, nginx serving the built frontend and proxying `/api`):

   ```bash
   docker compose -f docker-compose.prod.yml up --build -d
   docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
   ```

   > **This dev machine:** Avast's HTTPS scanning breaks TLS inside Docker
   > builds (see docs/data-source-limitations.md), so images cannot build
   > here until Web Shield HTTPS scanning is disabled. The prod compose is
   > written for a normal host. The native path (venv + `uvicorn --workers 2`
   > + `npm run build` served by any static server) works everywhere.
5. **Scheduler**: exactly one backend instance must run the scheduler. With
   `--workers 2`, APScheduler starts in each worker — for the daily jobs
   this is safe (every job is idempotent and guarded by database constraints)
   but wasteful; set `SCHEDULER_ENABLED=false` on extra instances if you
   scale out, keeping one dedicated scheduler process.
6. **Logs** are structured key-value lines without secrets; ship them
   wherever you like. Configuration is logged sanitized at startup.

## Backups (before any real reliance on the data)

The only state is Postgres (plus `.env`). Two complementary approaches:

### Logical dump (portable, small)

```bash
# Backup (run daily via cron/Task Scheduler; keep 14+ days)
docker exec stocks-db-1 pg_dump -U stocks -d stocks -Fc \
  > backups/stocks_$(date +%Y%m%d).dump

# Restore into a fresh database
docker exec -i stocks-db-1 pg_restore -U stocks -d stocks --clean --if-exists \
  < backups/stocks_20260719.dump
```

### Volume snapshot (fast, exact)

Stop the stack, copy the `pgdata` volume, restart:

```bash
docker compose stop db
docker run --rm -v stocks_pgdata:/data -v "$PWD/backups:/backup" alpine \
  tar czf /backup/pgdata_$(date +%Y%m%d).tar.gz -C /data .
docker compose start db
```

**Also back up `.env`** (it holds the credentials that make the dump usable)
to a password manager — not to the repository.

### What you can always rebuild

Prices, indicators, and signals are re-downloadable/recomputable from Yahoo
(idempotent sync + scan). What you **cannot** rebuild is trading history:
paper orders/positions/equity snapshots, backtest runs, competitions,
Telegram delivery logs. Backups exist for those.

## Operations runbook

- **Admin dashboard** (`/admin/data` in the UI): data health, scheduled jobs
  with next run times, manual triggers for every pipeline step, Telegram
  delivery status.
- **Manual pipeline** (equivalent of the nightly job):
  `POST /api/v1/admin/prices/sync` → `/admin/indicators/recalculate` →
  `/admin/signals/scan` → `/admin/telegram/queue` + `/process` →
  `/admin/paper/process`.
- **Everything is idempotent** — rerunning any step never duplicates data
  (database constraints enforce it), so the recovery procedure after any
  outage is simply: run the daily pipeline once.
- **Health**: `GET /api/v1/health` (liveness + DB + auth mode),
  `GET /api/v1/admin/data-health` (coverage), `GET /api/v1/admin/health-report`
  (staleness, stuck orders, Telegram failures).

## Upgrades

Dependencies are pinned in `backend/requirements.txt` and
`frontend/package-lock.json`. To upgrade: bump the pin, run the full test
suite (`pytest` — 110+ tests — plus `npm run lint && npm run build`), then
commit the new pin. Database schema changes always go through Alembic
(`alembic upgrade head` is part of every deploy).
