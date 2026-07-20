# 📈 Stock Market Analyst

A personal, **educational** stock-market research dashboard built with
[Streamlit](https://streamlit.io/). It is completely separate from the
FastAPI + React platform in this repo — its own stack, its own folder, its own
run command.

> **For education and personal research only.** It does **not** give buy/sell
> recommendations and is not financial advice. Market data may be delayed,
> incomplete, or incorrect.

## Pages

The Streamlit sidebar lists each section:

| Page | What it shows |
|------|---------------|
| **Home** (`app.py`) | Quick market snapshot + top headlines |
| **💹 Market Pulse** | Index/asset grid with sparklines, S&P 500 chart, sector heatmap, gainers/losers/most-active, headlines |
| **🔍 Stock Analyzer** | Company header, 4-view price chart, descriptive **Technical strength** & **Fundamental quality** gauges, "At a glance" chips, key-statistics grid, AI bull/bear + deep analysis |
| **🧺 ETF Analyzer** | Returns, risk gauge, sector breakdown, top holdings, and a **cost comparison** with cheaper peer alternatives |
| **🌍 Macro** | FRED indicators, the Treasury yield curve, and an AI macro pulse-check |
| **💼 Portfolio** | Local holdings, value & return, allocation & sector pies, portfolio risk, AI deep analysis |
| **📰 News** | Aggregated market headlines and by-ticker search |

## Data sources

- **Prices, fundamentals, ETF metadata, news** — [yfinance](https://github.com/ranaroussi/yfinance) (no key).
- **Macro indicators** — [FRED](https://fred.stlouisfed.org/) via `fredapi` (free key).
- **AI analysis** — Anthropic Claude (`claude-opus-4-8`), your own key.

Charts use **real indices** (`^GSPC`, `^NDX`, `^DJI`, `^RUT`, `^VIX`, `^TNX`,
`GC=F`, `CL=F`, `BTC-USD`, `DX-Y.NYB`), never ETF proxies. The 1-day view uses
**yesterday's close** as the baseline so overnight gaps don't distort the
green/red split.

## Setup

```bash
cd analyst
python -m venv .venv
# Windows:  .venv\Scripts\activate     macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env and add your keys (both optional)

streamlit run app.py
```

Both API keys are **optional**. Without `FRED_API_KEY` the Macro page shows a
notice; without `ANTHROPIC_API_KEY` the AI sections show a notice. Everything
else works from yfinance alone.

### Company logos (optional)

Logos are stored locally and embedded as data URLs at render time (no live
third-party fetch). Download them once:

```bash
python scripts/fetch_logos.py          # add --force to refresh existing files
```

Any ticker without a downloaded logo renders as a colored monogram badge, so
this step is purely cosmetic.

## Environment variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `ANTHROPIC_API_KEY` | AI analysis (Stock Analyzer, Macro, Portfolio) | optional |
| `FRED_API_KEY` | Macro indicators + yield curve | optional |

Keys are read from `.env` via `python-dotenv`. They are never printed or
committed (`.env`, `data/portfolio.json`, and `.streamlit/secrets.toml` are
git-ignored).

## Compliance framing

- No buy/hold/sell signals or recommendations anywhere.
- The Snapshot gauges are **descriptive** 0–100 scores ("Technical strength",
  "Fundamental quality"); chips use neutral language ("Firm momentum", "Higher
  than market", "Low multiple").
- Every page ends with the standard educational disclosure.
- AI output is constrained by a system prompt that forbids recommendations and
  price targets, and is fed already-computed facts (the model does no lookups).

## Known limitations

- yfinance is unofficial; fields (especially ETF holdings/sector weights and
  some fundamentals) are sometimes missing — widgets degrade to "—" rather than
  failing.
- Expense ratios use a curated table with a live-value fallback.
- "Most active" is approximated from last price × last volume over a curated
  large-cap universe, not an exchange tape.
- Intraday history is limited by Yahoo's lookback windows (5-minute bars ≈ 60
  days).
