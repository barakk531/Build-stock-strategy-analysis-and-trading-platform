"""Download company logos into assets/logos/<TICKER>.<ext> — run once, offline after.

Sources are tried in order and the best result kept (SVG preferred, else the
largest raster):

  1. simple-icons via jsdelivr CDN (crisp monochrome SVG, recolored to white
     for the dark theme)
  2. vectorlogo.zone (brand SVG)
  3. apple-touch-icon from the company domain
  4. Google faviconV2 at size 256
  5. DuckDuckGo icons

At render time the app only reads these local files (lib/logos.py) — it never
fetches a third party live. Re-run any time to refresh; existing files are
skipped unless --force is passed.

Usage:
    python scripts/fetch_logos.py [--force]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Make `lib` importable when run as a script from anywhere.
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

try:  # OS trust store so HTTPS works behind AV/proxy inspection
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import requests  # noqa: E402

from lib.logos import TICKER_DOMAINS  # noqa: E402

LOGOS_DIR = APP_DIR / "assets" / "logos"
HEADERS = {"User-Agent": "Mozilla/5.0 (market-analyst logo fetcher)"}
TIMEOUT = 12
MIN_BYTES = 200
MAX_BYTES = 400_000

# ETFs and a few names simple-icons/vectorlogo cover by brand slug.
BRAND_SLUGS = {
    "AAPL": "apple", "MSFT": "microsoft", "GOOGL": "google", "GOOG": "google",
    "AMZN": "amazon", "NVDA": "nvidia", "META": "meta", "TSLA": "tesla",
    "NFLX": "netflix", "ADBE": "adobe", "CRM": "salesforce", "ORCL": "oracle",
    "IBM": "ibm", "INTC": "intel", "AMD": "amd", "CSCO": "cisco", "QCOM": "qualcomm",
    "PYPL": "paypal", "V": "visa", "MA": "mastercard", "DIS": "waltdisney",
    "KO": "coca-cola", "PEP": "pepsi", "MCD": "mcdonalds", "SBUX": "starbucks",
    "NKE": "nike", "UBER": "uber", "SHOP": "shopify", "SNOW": "snowflake",
    "PLTR": "palantir", "COIN": "coinbase", "SPOT": "spotify", "ABNB": "airbnb",
}


def _sanitize(ticker: str) -> str:
    return ticker.replace("^", "_").replace("=", "_").replace("/", "_")


def _get(url: str) -> tuple[bytes, str] | None:
    """(content, ext) if the URL returns a plausible image, else None."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except Exception:
        return None
    if resp.status_code != 200 or not resp.content:
        return None
    body = resp.content
    if not (MIN_BYTES <= len(body) <= MAX_BYTES):
        return None
    ctype = resp.headers.get("content-type", "").lower()
    if "svg" in ctype or body[:5].lstrip().startswith(b"<svg") or url.endswith(".svg"):
        return body, ".svg"
    if "png" in ctype or body[:8] == b"\x89PNG\r\n\x1a\n":
        return body, ".png"
    if "x-icon" in ctype or "ico" in ctype or body[:4] == b"\x00\x00\x01\x00":
        return body, ".ico"
    if "jpeg" in ctype or body[:3] == b"\xff\xd8\xff":
        return body, ".jpg"
    if "webp" in ctype or body[8:12] == b"WEBP":
        return body, ".webp"
    return None


def _whiten_svg(svg: bytes) -> bytes:
    """Recolor a monochrome simple-icons SVG to white for the dark theme."""
    text = svg.decode("utf-8", "ignore")
    text = re.sub(r'fill="[^"]*"', 'fill="#ffffff"', text)
    if "fill=" not in text:
        text = text.replace("<svg", '<svg fill="#ffffff"', 1)
    return text.encode("utf-8")


def candidates(ticker: str) -> list[tuple[str, bool]]:
    """(url, is_simpleicons_svg) sources to try for this ticker."""
    urls: list[tuple[str, bool]] = []
    slug = BRAND_SLUGS.get(ticker)
    if slug:
        urls.append((f"https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg", True))
        urls.append((f"https://www.vectorlogo.zone/logos/{slug}/{slug}-icon.svg", False))
    domain = TICKER_DOMAINS.get(ticker)
    if domain:
        urls.append((f"https://{domain}/apple-touch-icon.png", False))
        urls.append((f"https://www.google.com/s2/favicons?domain={domain}&sz=256", False))
        urls.append((f"https://icons.duckduckgo.com/ip3/{domain}.ico", False))
    return urls


def fetch_one(ticker: str, force: bool) -> str:
    safe = _sanitize(ticker)
    if not force:
        for ext in (".svg", ".png", ".webp", ".jpg", ".ico"):
            if (LOGOS_DIR / f"{safe}{ext}").exists():
                return "skip"

    best: tuple[bytes, str] | None = None
    for url, is_si in candidates(ticker):
        got = _get(url)
        if got is None:
            continue
        content, ext = got
        if is_si and ext == ".svg":
            content = _whiten_svg(content)
        # Prefer the first SVG; otherwise keep the largest raster seen.
        if ext == ".svg":
            best = (content, ext)
            break
        if best is None or len(content) > len(best[0]):
            best = (content, ext)

    if best is None:
        return "miss"
    for old in LOGOS_DIR.glob(f"{safe}.*"):
        old.unlink(missing_ok=True)
    (LOGOS_DIR / f"{safe}{best[1]}").write_bytes(best[0])
    return "ok"


def main() -> None:
    force = "--force" in sys.argv
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    tickers = sorted(set(TICKER_DOMAINS) | set(BRAND_SLUGS))
    counts = {"ok": 0, "skip": 0, "miss": 0}
    for ticker in tickers:
        result = fetch_one(ticker, force)
        counts[result] += 1
        marker = {"ok": "✓", "skip": "·", "miss": "✗"}[result]
        print(f"  {marker} {ticker}")
    print(f"\nDone: {counts['ok']} downloaded, {counts['skip']} skipped, {counts['miss']} unavailable.")
    print("Missing logos render as a colored monogram badge — no action needed.")


if __name__ == "__main__":
    main()
