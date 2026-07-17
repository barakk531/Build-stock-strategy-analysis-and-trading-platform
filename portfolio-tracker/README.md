# Portfolio Tracker

Tracks stock holdings from a transaction log: current value, unrealized gains,
and realized gains from sales. Prices come from Yahoo Finance via `yfinance`.

> **Note:** this project used to live at the repository root and was moved here
> when the Stock Strategy Platform took over the root. A historical `.venv` may
> still exist at the repo root; virtualenvs are not relocatable, so either keep
> invoking it (`..\.venv\Scripts\python main.py`) or recreate one here with the
> Setup steps below.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows
pip install -r requirements.txt
cp transactions.example.csv transactions.csv
```

## Usage

```bash
python main.py                  # reads transactions.csv
python main.py -f other.csv     # or point it somewhere else
```

```
TICKER      SHARES    AVG COST       PRICE         VALUE          GAIN    GAIN %
--------------------------------------------------------------------------------
AAPL            15      193.00      333.26      4,998.90     +2,103.95     72.7%
MSFT             3      401.20      401.10      1,203.30         -0.30     -0.0%
--------------------------------------------------------------------------------
TOTAL                                           6,202.20     +2,103.65     51.3%
```

## The transaction log

You record **transactions**, not positions — positions are derived. This is
deliberate: cost basis and realized gains are a function of your buy/sell
history, so a file listing only "15 shares of AAPL" can't reconstruct them.

| column   | meaning                                  |
| -------- | ---------------------------------------- |
| `date`   | trade date, `YYYY-MM-DD`                 |
| `ticker` | symbol, e.g. `AAPL`                      |
| `action` | `buy` or `sell`                          |
| `shares` | always positive; `sell` reduces position |
| `price`  | price per share                          |
| `fees`   | commission — added to a buy's basis, subtracted from a sell's proceeds |

## Cost basis method

Uses **average cost**: each buy re-averages the basis across all shares held; a
sell realizes gain against that average and leaves it unchanged.

FIFO and specific-lot are the other permissible methods, and they produce
different realized-gain numbers. If you intend to use these figures for taxes,
confirm this matches the method your broker reports.

## Testing

```bash
python -m pytest tests/ -q
```

## Note on HTTPS and antivirus

Avast is intercepting HTTPS on this machine — it re-signs traffic with its own
root CA, which lives in the Windows certificate store. Python ships its own CA
bundle (certifi) and doesn't consult that store, so price fetches fail with
`CERTIFICATE_VERIFY_FAILED` out of the box.

`portfolio/certs.py` handles this by generating a bundle of certifi + the
Windows roots on first run, so **certificate verification stays fully enabled**.
The alternative fix you'll find online — `verify=False` — disables verification
for every request and is not used here.

One caveat: this works because `yfinance` uses `curl_cffi` (BoringSSL). The
Avast root marks `basicConstraints` non-critical, which RFC 5280 forbids for a
CA, and OpenSSL 3 rejects it outright. So if you add a library that uses stdlib
`ssl` or `requests`, it will still fail against an intercepted connection. The
durable fix is to turn off Avast's HTTPS scanning
(Settings → Protection → Core Shields → Web Shield → *Enable HTTPS scanning*).

## Layout

```
main.py                 CLI entry point
portfolio/
  transactions.py       load + validate the CSV
  positions.py          replay transactions into positions & realized gains
  prices.py             fetch quotes
  report.py             format the table
  certs.py              Windows trust store workaround (see above)
tests/
```

## Possible next steps

- Sector / allocation breakdown
- Dividend tracking (a `dividend` action in the log)
- Historical value chart — needs date-indexed prices, which `yfinance` already returns
- Import from your broker's CSV export
- Streamlit UI: `streamlit run app.py`
