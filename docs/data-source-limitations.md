# Data-source limitations

## Yahoo Finance (via yfinance)

- Unofficial API: no SLA, occasional throttling, schema drift. Downloads use
  retries with exponential backoff and per-symbol failure logging (Phase 2).
- Data may be delayed, revised, or missing. The daily sync re-fetches a small
  overlap window to pick up revisions rather than trusting old rows forever.
- Ticker formatting differs (e.g. `BRK.B` → `BRK-B`); the universe sync stores
  both the canonical and Yahoo symbols.
- Adjusted close is used for indicators by default (documented in
  strategy-rules.md). Downloads run with `auto_adjust=False` so both the raw
  close and the adjusted close are stored; when Yahoo omits the adjusted value
  for a row, it falls back to the raw close.
- The daily sync re-fetches a trailing overlap window (default 5 days) and
  upserts, so revised rows overwrite quietly and reruns never duplicate
  (unique `stock_id + trade_date`).

## S&P 500 membership

The constituent list is synced from public sources and refreshed weekly.
Removed members are marked inactive, never deleted. Version 1 knows only the
**current** membership — see backtesting-assumptions.md for the survivorship
bias this creates.

## Market capitalization

Metadata (market cap, sector, industry) is refreshed periodically, not daily
per page load, and reflects the present — not historical values.

## This machine: Avast HTTPS interception

Avast antivirus intercepts HTTPS on the development machine, re-signing
traffic with its own root CA. That root is in the Windows certificate store
but not in Python's bundled certifi, and it violates RFC 5280 (non-critical
basicConstraints on a CA), so **OpenSSL 3 rejects it outright** — stdlib
`ssl`/`requests` fail even if the root is added to a bundle.

`yfinance` uses `curl_cffi` (BoringSSL), which accepts a bundle of
certifi + the Windows roots. The proven workaround lives in
`portfolio-tracker/portfolio/certs.py` (generate the bundle, point
`CURL_CA_BUNDLE` at it) and will be ported into the backend in Phase 2.

**Docker is affected too** (verified 2026-07-17): all traffic leaving the
Docker Desktop VM (WSL2) is intercepted, with or without the injected
`http.docker.internal:3128` proxy. Image *pulls* succeed, but `pip install` /
`npm ci` inside image builds fail certificate verification — and adding the
Avast root to the container is useless because OpenSSL 3 rejects it. Host-native
pip and npm currently work. Until HTTPS scanning is disabled, local dev runs
hybrid: Postgres in Docker, backend + frontend native (see README).

The durable machine-level fix is disabling Avast's HTTPS scanning:
Settings → Protection → Core Shields → Web Shield → *Enable HTTPS scanning*.
Never use `verify=False` — it disables certificate checking entirely.
