"""Shared configuration for the Stock Market Analyst dashboard.

Loads API keys from the project-root .env (python-dotenv) and exposes the
compliance disclosure shown in every page footer. Import this module first in
every entry point — it also installs the OS trust store for TLS so the app
works behind corporate/AV HTTPS inspection (e.g. Avast) without ever
disabling certificate verification.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- TLS: trust the OS certificate store (never verify=False) ---------------
# Some machines (antivirus HTTPS scanning, corporate proxies) re-sign TLS
# traffic with a certificate that lives in the Windows/macOS trust store but
# not in certifi's bundle. truststore makes Python's SSL use the OS store so
# yfinance / FRED / Anthropic requests keep full verification.
try:  # optional — the app still works without it on machines with clean TLS
    import truststore

    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - best-effort platform shim
    pass

# --- Environment -------------------------------------------------------------
from dotenv import load_dotenv  # noqa: E402  (after TLS shim on purpose)

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
ASSETS_DIR = APP_DIR / "assets"
LOGOS_DIR = ASSETS_DIR / "logos"

# .env lives in the analyst/ app root; a repo-root .env is also honored so the
# dashboard can share keys with sibling projects. Neither file is committed.
load_dotenv(APP_DIR / ".env")
load_dotenv(APP_DIR.parent / ".env")


def anthropic_api_key() -> str | None:
    """ANTHROPIC_API_KEY from the environment, or None (never raises)."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def fred_api_key() -> str | None:
    """FRED_API_KEY from the environment, or None (never raises)."""
    return os.environ.get("FRED_API_KEY") or None


# --- Compliance (non-negotiable) ---------------------------------------------
DISCLOSURE = (
    "This dashboard is for educational and informational purposes only. "
    "It is not financial advice, not a recommendation to buy or sell any "
    "security, and is not personalized to your situation. Consult a licensed "
    "advisor before making investment decisions."
)

APP_NAME = "Stock Market Analyst"
SIDEBAR_BRAND = "📈 Market Analyst"

# Base font bump for accessibility + dark-theme polish shared by all pages.
BASE_CSS = """
<style>
  .main .block-container { font-size: 17px; }
  footer { visibility: hidden; }
  .disclosure {
    margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #383835;
    color: #898781; font-size: 13px; line-height: 1.5;
  }
</style>
"""


def apply_chrome(st) -> None:
    """Sidebar branding + base CSS. Call at the top of every page."""
    st.sidebar.markdown(f"### {SIDEBAR_BRAND}")
    st.markdown(BASE_CSS, unsafe_allow_html=True)


def render_disclosure(st) -> None:
    """Compliance footer. Call at the bottom of every page."""
    st.markdown(
        f'<div class="disclosure">{DISCLOSURE}<br>'
        "Data source: Yahoo Finance (delayed) and FRED. Figures may be delayed, "
        "incomplete, or incorrect.</div>",
        unsafe_allow_html=True,
    )


# --- Formatting (shared by all pages) ----------------------------------------

UP_COLOR = "#34d399"
DOWN_COLOR = "#f87171"
FLAT_COLOR = "#c3c2b7"


def fmt_price(value) -> str:
    if value is None:
        return "—"
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):+.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def fmt_big(value) -> str:
    """Readable magnitude: $950M, $12.4B, $2.1T."""
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if number < 0 else ""
    number = abs(number)
    for unit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if number >= unit:
            return f"{sign}${number / unit:.1f}{suffix}".replace(".0", "")
    return f"{sign}${number:,.0f}"


def fmt_ratio(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def change_color(value) -> str:
    if value is None:
        return FLAT_COLOR
    try:
        number = float(value)
    except (TypeError, ValueError):
        return FLAT_COLOR
    if number > 0:
        return UP_COLOR
    if number < 0:
        return DOWN_COLOR
    return FLAT_COLOR
