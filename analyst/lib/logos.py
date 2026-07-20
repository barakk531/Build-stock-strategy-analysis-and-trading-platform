"""Company logos: local files only at render time (no live third-party fetch).

scripts/fetch_logos.py downloads logos into assets/logos/<TICKER>.<ext> ahead
of time; here we just embed them as base64 data URLs. Missing logos degrade to
a neutral monogram badge so layouts never break.
"""

from __future__ import annotations

import base64
import html
import re
from functools import lru_cache

from lib.config import LOGOS_DIR

_TICKER_RE = re.compile(r"^[A-Z0-9.\-^=]{1,12}$")

_MIME = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".webp": "image/webp",
}

# Ticker -> company domain, used by scripts/fetch_logos.py (favicon sources)
# and kept here so the app and the script share one map.
TICKER_DOMAINS: dict[str, str] = {
    "AAPL": "apple.com", "MSFT": "microsoft.com", "GOOGL": "abc.xyz", "GOOG": "abc.xyz",
    "AMZN": "amazon.com", "NVDA": "nvidia.com", "META": "meta.com", "TSLA": "tesla.com",
    "BRK-B": "berkshirehathaway.com", "AVGO": "broadcom.com", "LLY": "lilly.com",
    "JPM": "jpmorganchase.com", "V": "visa.com", "XOM": "exxonmobil.com", "UNH": "unitedhealthgroup.com",
    "MA": "mastercard.com", "PG": "pg.com", "COST": "costco.com", "JNJ": "jnj.com",
    "HD": "homedepot.com", "WMT": "walmart.com", "ABBV": "abbvie.com", "NFLX": "netflix.com",
    "BAC": "bankofamerica.com", "CRM": "salesforce.com", "ORCL": "oracle.com", "CVX": "chevron.com",
    "MRK": "merck.com", "KO": "coca-colacompany.com", "AMD": "amd.com", "PEP": "pepsico.com",
    "ACN": "accenture.com", "LIN": "linde.com", "TMO": "thermofisher.com", "MCD": "mcdonalds.com",
    "CSCO": "cisco.com", "ADBE": "adobe.com", "IBM": "ibm.com", "GE": "ge.com",
    "ABT": "abbott.com", "DHR": "danaher.com", "TXN": "ti.com", "QCOM": "qualcomm.com",
    "INTU": "intuit.com", "AMAT": "appliedmaterials.com", "CAT": "caterpillar.com",
    "VZ": "verizon.com", "T": "att.com", "DIS": "thewaltdisneycompany.com", "WFC": "wellsfargo.com",
    "PFE": "pfizer.com", "NEE": "nexteraenergy.com", "PM": "pmi.com", "MS": "morganstanley.com",
    "GS": "goldmansachs.com", "RTX": "rtx.com", "UNP": "up.com", "CMCSA": "corporate.comcast.com",
    "COP": "conocophillips.com", "AXP": "americanexpress.com", "SPGI": "spglobal.com",
    "UBER": "uber.com", "HON": "honeywell.com", "BKNG": "bookingholdings.com", "LOW": "lowes.com",
    "ISRG": "intuitive.com", "ETN": "eaton.com", "BLK": "blackrock.com", "PGR": "progressive.com",
    "SYK": "stryker.com", "VRTX": "vrtx.com", "TJX": "tjx.com", "C": "citigroup.com",
    "BSX": "bostonscientific.com", "ADP": "adp.com", "MDT": "medtronic.com", "SBUX": "starbucks.com",
    "GILD": "gilead.com", "MMC": "mmc.com", "SCHW": "schwab.com", "LMT": "lockheedmartin.com",
    "ADI": "analog.com", "CB": "chubb.com", "MU": "micron.com", "AMT": "americantower.com",
    "PLD": "prologis.com", "DE": "deere.com", "BA": "boeing.com", "SO": "southerncompany.com",
    "MO": "altria.com", "ELV": "elevancehealth.com", "INTC": "intel.com", "NKE": "nike.com",
    "PANW": "paloaltonetworks.com", "PLTR": "palantir.com", "NOW": "servicenow.com",
    "SNOW": "snowflake.com", "SHOP": "shopify.com", "SQ": "block.xyz", "PYPL": "paypal.com",
    "ABNB": "airbnb.com", "COIN": "coinbase.com", "MRNA": "modernatx.com", "F": "ford.com",
    "GM": "gm.com", "DAL": "delta.com", "UAL": "united.com", "AAL": "aa.com",
    "CVS": "cvshealth.com", "TGT": "target.com", "KHC": "kraftheinzcompany.com",
    "MDLZ": "mondelezinternational.com", "CL": "colgatepalmolive.com", "KMB": "kimberly-clark.com",
    "GIS": "generalmills.com", "DUK": "duke-energy.com", "D": "dominionenergy.com",
    "EXC": "exeloncorp.com", "AEP": "aep.com", "SRE": "sempra.com", "O": "realtyincome.com",
    "SPG": "simon.com", "CCI": "crowncastle.com", "EQIX": "equinix.com", "CSX": "csx.com",
    "NSC": "norfolksouthern.com", "FDX": "fedex.com", "UPS": "ups.com", "EMR": "emerson.com",
    "ITW": "itw.com", "GD": "gd.com", "NOC": "northropgrumman.com", "MMM": "3m.com",
    "DOW": "dow.com", "DD": "dupont.com", "FCX": "fcx.com", "NEM": "newmont.com",
    "SLB": "slb.com", "EOG": "eogresources.com", "OXY": "oxy.com", "PSX": "phillips66.com",
    "MPC": "marathonpetroleum.com", "VLO": "valero.com", "HOOD": "robinhood.com",
    "DASH": "doordash.com", "MELI": "mercadolibre.com", "ANET": "arista.com", "KLAC": "kla.com",
    "LRCX": "lamresearch.com", "SNPS": "synopsys.com", "CDNS": "cadence.com", "MRVL": "marvell.com",
}


def _logo_path(ticker: str):
    if not _TICKER_RE.match(ticker or ""):
        return None
    safe = ticker.replace("^", "_").replace("=", "_").replace("/", "_")
    for ext in (".svg", ".png", ".webp", ".jpg", ".jpeg", ".ico"):
        path = LOGOS_DIR / f"{safe}{ext}"
        if path.is_file():
            return path
    return None


@lru_cache(maxsize=512)
def logo_data_url(ticker: str) -> str | None:
    """data: URL for a locally stored logo, or None if not downloaded."""
    path = _logo_path((ticker or "").upper())
    if path is None:
        return None
    try:
        raw = path.read_bytes()
        if len(raw) > 512_000:  # sanity cap — logos should be tiny
            return None
        mime = _MIME.get(path.suffix.lower(), "image/png")
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        return None


_PALETTE = ["#3987e5", "#008300", "#d55181", "#c98500", "#199e70", "#d95926", "#9085e9", "#e66767"]


def logo_html(ticker: str, size: int = 24) -> str:
    """<img> tag for the logo, or a monogram badge fallback. Safe for st.markdown."""
    ticker = (ticker or "?").upper()
    url = logo_data_url(ticker)
    if url:
        return (
            f'<img src="{url}" width="{size}" height="{size}" '
            f'style="border-radius:6px;object-fit:contain;vertical-align:middle;background:#ffffff10" />'
        )
    color = _PALETTE[sum(ord(c) for c in ticker) % len(_PALETTE)]
    initial = html.escape(ticker[0]) if ticker else "?"
    return (
        f'<span style="display:inline-flex;width:{size}px;height:{size}px;border-radius:6px;'
        f"background:{color};color:#fff;font-weight:700;font-size:{max(10, size // 2)}px;"
        f'align-items:center;justify-content:center;vertical-align:middle">{initial}</span>'
    )
