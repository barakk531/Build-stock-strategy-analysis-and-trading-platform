# Stock Strategy Platform

Full-stack S&P 500 technical-analysis platform: daily Yahoo Finance data,
configurable SMA-trend + volume strategies, buy/sell signal detection,
backtesting, multi-account paper trading, and Telegram alerts.

**Status: Phase 7 (paper trading) complete.** Working end to end: S&P 500
universe + 20 years of daily history (idempotent sync), SMA 20/50/150 +
volume indicators, transition-mode buy/sell signal detection, the scanner UI,
per-stock charts with historical signal markers, Telegram alerts with
duplicate-proof delivery, a full portfolio backtester (next-open fills,
split-adjusted, benchmark-relative), and multi-account paper trading —
independent simulated accounts that trade their strategy's signals
automatically (raw-price fills, split/dividend handling, complete order audit
trail, daily equity snapshots) driven by scheduled jobs on the
America/New_York market clock. Strategy competition arrives in Phase 8 — see
the phase map in [docs/architecture.md](docs/architecture.md).

Key endpoints (see `/docs` for all):

```text
GET  /api/v1/scanner                  # filter/sort all stocks + buy/sell states
POST /api/v1/backtests                # launch a backtest (background)
GET  /api/v1/backtests/{id}           # status + results (metrics, curves)
POST /api/v1/paper-accounts           # create an auto-trading paper account
GET  /api/v1/paper-accounts/{id}/performance   # full account statistics
POST /api/v1/admin/paper/process      # advance all accounts manually
GET  /api/v1/admin/jobs               # scheduled jobs + next run times
POST /api/v1/admin/universe/sync      # refresh S&P 500 membership
POST /api/v1/admin/prices/sync        # backfill/incremental daily prices
POST /api/v1/admin/stocks/add         # track an extra/benchmark symbol (^GSPC)
GET  /api/v1/admin/data-health        # coverage, staleness, gaps
GET  /api/v1/stocks/AAPL/prices       # daily OHLCV series
```

> This platform is for research, education, technical analysis, and simulated
> paper trading only. It does not provide personalized financial advice and
> does not guarantee investment results. Market data may be delayed,
> incomplete, or incorrect. Past or simulated performance does not guarantee
> future results.

## Stack

- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16,
  APScheduler
- **Frontend:** React (JavaScript), Vite, React Router, TanStack Query,
  Axios, Zustand, Tailwind CSS 4; charts (Phase 4) via TradingView
  Lightweight Charts

## Quickstart (Docker)

> ⚠️ **On this dev machine the image build currently fails** — Avast intercepts
> HTTPS for Docker Desktop VM traffic and `pip install` inside the build can't
> verify pypi.org. Use [Native development](#native-development) below until
> Avast's HTTPS scanning is disabled. Details under Known limitations.

```bash
cp .env.example .env        # defaults work for local dev
docker compose up --build -d
docker compose exec backend alembic upgrade head
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

The compose file is dev-oriented: backend and frontend source is
volume-mounted with hot reload.

## Native development

Postgres can stay in Docker while both apps run on the host:

```bash
docker compose up -d db
```

Backend (from `backend/`):

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend (from `frontend/`):

```bash
npm install
npm run dev                       # proxies /api → http://localhost:8000
```

## Tests & checks

```bash
# backend (from backend/)
pytest                # unit tests; DB integration test runs when DATABASE_URL is set
ruff check .

# frontend (from frontend/)
npm run lint
npm run build
```

Automated tests never call live Yahoo or Telegram services.

## Migrations

```bash
# from backend/ (or: docker compose exec backend <cmd>)
alembic upgrade head                           # apply
alembic revision --autogenerate -m "message"   # create after model changes
```

Every schema change goes through a migration.

## Repository layout

```
backend/            FastAPI app (api → services → repositories → models)
frontend/           React SPA
docs/               architecture, strategy rules, backtesting assumptions,
                    data-source limitations
portfolio-tracker/  older standalone CLI portfolio tracker (separate project)
docker-compose.yml  db + backend + frontend for local dev
.env.example        environment template — copy to .env; never commit .env
```

## Known limitations (v1)

- Backtests use the **current** S&P 500 membership → survivorship bias
  (see [docs/backtesting-assumptions.md](docs/backtesting-assumptions.md)).
- Market-cap filters use today's values, not historical ones.
- No authentication yet (arrives in Phase 9); don't expose ports publicly.
- **`docker compose up --build` fails on this dev machine** (verified
  2026-07-17): Avast intercepts HTTPS for all Docker Desktop VM traffic, and
  OpenSSL 3 rejects its re-signing root, so `pip install` inside image builds
  cannot verify pypi.org. Native pip/npm on the host work fine. Until Avast's
  HTTPS scanning is disabled (Settings → Protection → Core Shields → Web
  Shield → *Enable HTTPS scanning*), use the hybrid setup:
  `docker compose up -d db` plus native backend and frontend. Details:
  [docs/data-source-limitations.md](docs/data-source-limitations.md).

Data source: Yahoo Finance (unofficial). All accounts are simulated — no real
orders are ever placed.
