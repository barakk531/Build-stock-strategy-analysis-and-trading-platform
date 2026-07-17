"""Building a CA bundle that includes the Windows certificate store.

Avast (and other antivirus/corporate proxies) intercept HTTPS by re-signing
traffic with their own root CA. That root lives in the Windows certificate
store, which browsers consult but Python does not — Python ships certifi, which
has never heard of it. Without this module, every price fetch fails with
CERTIFICATE_VERIFY_FAILED.

We fix that by trusting the same roots Windows already trusts, rather than by
disabling verification. Note this only works for callers backed by BoringSSL
(curl_cffi, which yfinance uses): the Avast root marks basicConstraints
non-critical, which RFC 5280 forbids for a CA, and OpenSSL 3 rejects it outright.
So stdlib ssl / requests will still fail against an intercepted connection.
"""

from __future__ import annotations

import ssl
from pathlib import Path

import certifi

BUNDLE = Path(__file__).resolve().parent.parent / "certs" / "win-ca-bundle.pem"


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
    """Write (once) and return a CA bundle path, or None if not needed.

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
