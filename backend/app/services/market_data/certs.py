"""CA bundle including the Windows certificate store, for TLS behind interception.

Ported from the portfolio-tracker project (proven on this machine). Avast (and
corporate proxies) intercept HTTPS by re-signing traffic with their own root CA,
which lives in the Windows store but not in certifi — so Python network calls
fail with CERTIFICATE_VERIFY_FAILED out of the box.

This trusts the same roots Windows already trusts, keeping verification ON. It
only helps callers backed by BoringSSL (curl_cffi, which yfinance uses): the
Avast root marks basicConstraints non-critical, which RFC 5280 forbids for a CA,
so OpenSSL 3 (stdlib ssl / requests) rejects it outright even with this bundle.
Anything on this path must therefore go through curl_cffi, not stdlib ssl.
"""

from __future__ import annotations

import logging
import os
import ssl
from pathlib import Path

import certifi

logger = logging.getLogger(__name__)

# backend/app/services/market_data/certs.py -> backend/certs/win-ca-bundle.pem
BUNDLE = Path(__file__).resolve().parents[3] / "certs" / "win-ca-bundle.pem"


def _windows_roots() -> list[str]:
    pems: list[str] = []
    for store in ("ROOT", "CA"):
        try:
            certs = ssl.enum_certificates(store)
        except (AttributeError, OSError):
            return []  # not Windows, or store unreadable
        for der, encoding, _trust in certs:
            if encoding == "x509_asn":
                pems.append(ssl.DER_cert_to_PEM_cert(der))
    return pems


def ensure_bundle(refresh: bool = False) -> str | None:
    """Write (once) and return a CA bundle path, or None when not needed.

    Returns None off Windows, where certifi alone is correct.
    """
    roots = _windows_roots()
    if not roots:
        return None

    if refresh or not BUNDLE.exists():
        BUNDLE.parent.mkdir(parents=True, exist_ok=True)
        body = [Path(certifi.where()).read_text(encoding="utf-8"), *roots]
        BUNDLE.write_text("\n".join(body), encoding="utf-8")

    return str(BUNDLE)


def trust_windows_roots() -> None:
    """Point curl_cffi at the Windows trust store if TLS here is intercepted.

    Idempotent and safe to call before every download. No-op off Windows.
    """
    bundle = ensure_bundle()
    if bundle:
        os.environ.setdefault("CURL_CA_BUNDLE", bundle)
        os.environ.setdefault("SSL_CERT_FILE", bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)
        logger.debug("market_data tls=windows-bundle path=%s", bundle)
