"""Google ID-token verification — no external dependency beyond httpx (already present).

Calls Google's tokeninfo endpoint over TLS to validate the credential the browser
receives from Google Identity Services.  Trade-off vs. local signature check: one
network round-trip per Google login, no cert/JWK management.  Swappable later.

Public interface:
    verify_google_token(credential) -> GoogleIdentity | None
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from .config import GOOGLE_CLIENT_ID

_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str          # stable Google user id — use as the join key
    email: str
    name: str
    picture: Optional[str]
    email_verified: bool


def verify_google_token(credential: str) -> Optional[GoogleIdentity]:
    """Return the verified identity or None on any failure.

    Returns None (instead of raising) so the caller can return a clean 401
    without leaking internals.  Failures are logged at DEBUG so we can diagnose
    without filling prod logs on every retry.
    """
    if not GOOGLE_CLIENT_ID:
        return None
    try:
        res = httpx.get(_TOKENINFO_URL, params={"id_token": credential}, timeout=8.0)
        if res.status_code != 200:
            return None
        payload = res.json()
    except Exception:
        return None

    # Validate audience and issuer — critical; never skip.
    if payload.get("aud") != GOOGLE_CLIENT_ID:
        return None
    if payload.get("iss") not in _VALID_ISSUERS:
        return None
    if payload.get("email_verified") not in (True, "true"):
        return None

    return GoogleIdentity(
        sub=payload["sub"],
        email=payload["email"].strip().lower(),
        name=payload.get("name", ""),
        picture=payload.get("picture"),
        email_verified=True,
    )
