"""Thin Telegram Bot API client, isolated from strategy and alert logic.

Uses curl_cffi (BoringSSL) instead of stdlib TLS so it works behind this
machine's Avast HTTPS interception, with verification fully enabled via the
Windows-store bundle. Messages use HTML parse mode; escape user-ish text with
escape_html before interpolating.
"""

from __future__ import annotations

import html
import logging

from app.core.config import get_settings
from app.services.market_data import certs

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org"


class TelegramError(Exception):
    """Raised when the Bot API rejects or fails a send."""


def escape_html(value: object) -> str:
    return html.escape(str(value), quote=False)


def send_message(text: str, *, disable_preview: bool = True) -> str:
    """Send `text` to the configured chat. Returns the Telegram message id.

    Raises TelegramError on missing config, transport failure, or API error.
    Credentials never appear in logs or error messages.
    """
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise TelegramError("Telegram is not configured (bot token / chat id missing)")

    certs.trust_windows_roots()
    from curl_cffi import requests as curl_requests  # lazy: TLS env must be set first

    url = f"{_API}/bot{settings.telegram_bot_token}/sendMessage"
    try:
        response = curl_requests.post(
            url,
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": disable_preview,
            },
            timeout=15,
        )
    except Exception as exc:  # network-level failure
        raise TelegramError(f"Telegram transport error: {exc.__class__.__name__}") from exc

    try:
        payload = response.json()
    except Exception as exc:
        raise TelegramError(f"Telegram returned non-JSON (HTTP {response.status_code})") from exc

    if not payload.get("ok"):
        description = payload.get("description", "unknown error")
        raise TelegramError(f"Telegram API error (HTTP {response.status_code}): {description}")

    message_id = payload.get("result", {}).get("message_id")
    logger.info("telegram sent message_id=%s", message_id)
    return str(message_id)
