"""API-key authentication (spec §20: protect administration endpoints).

Single-operator model: one key from the ADMIN_API_KEY environment variable
guards the admin router and every mutating endpoint. When no key is
configured, auth is DISABLED for local development — a warning is logged at
startup and /health reports auth_required=false so the UI can surface it.
Comparison is constant-time; the key never appears in logs or config dumps.
"""

from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def auth_required() -> bool:
    return bool(get_settings().admin_api_key)


def require_admin(api_key: Annotated[str | None, Depends(_header)]) -> None:
    configured = get_settings().admin_api_key
    if not configured:
        return  # development mode — auth disabled
    # compare_digest(str, str) raises TypeError on non-ASCII input; encoding
    # to bytes first keeps the comparison constant-time for any Unicode key
    # instead of turning a wrong-but-valid config into a 500.
    valid = api_key is not None and secrets.compare_digest(
        api_key.encode("utf-8"), configured.encode("utf-8")
    )
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key (X-API-Key header)",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def warn_if_disabled() -> None:
    if not auth_required():
        logger.warning(
            "ADMIN_API_KEY not set — admin and mutating endpoints are UNPROTECTED. "
            "Fine for local development; required before any public deployment."
        )
