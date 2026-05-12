"""
clerk_auth.py — Clerk JWT verification for poet.horse.

Clerk issues RS256 JWTs. We verify them against Clerk's JWKS endpoint
(cached in-process, refreshed every hour or on key-id miss).

Exports:
  CLERK_PUBLISHABLE_KEY  — injected into every template
  verify_clerk_token(token) → clerk_user_id | None
"""

import os
import threading
import time

import requests as _req

CLERK_SECRET_KEY      = os.environ.get('CLERK_SECRET_KEY', '')
CLERK_PUBLISHABLE_KEY = os.environ.get('CLERK_PUBLISHABLE_KEY', '')

# ── JWKS cache ─────────────────────────────────────────────────────────────────
# Keys rotate rarely; we cache for 1 hour and force-refresh on key-id miss.

_jwks_lock    = threading.Lock()
_jwks_keys: list = []          # list of JWK dicts, keyed by 'kid'
_jwks_fetched = 0.0
_JWKS_TTL     = 3600.0


def _fetch_jwks(force: bool = False) -> list:
    global _jwks_keys, _jwks_fetched
    now = time.time()
    with _jwks_lock:
        if not force and _jwks_keys and (now - _jwks_fetched) < _JWKS_TTL:
            return _jwks_keys
        try:
            resp = _req.get(
                'https://api.clerk.com/v1/jwks',
                headers={'Authorization': f'Bearer {CLERK_SECRET_KEY}'},
                timeout=5,
            )
            resp.raise_for_status()
            _jwks_keys   = resp.json().get('keys', [])
            _jwks_fetched = now
        except Exception:
            pass  # return stale keys if fetch fails
        return _jwks_keys


def verify_clerk_token(token: str) -> str | None:
    """
    Verify a Clerk session JWT and return the Clerk user ID (the 'sub' claim).
    Returns None on any failure so callers can treat it as "not authenticated".

    We do NOT raise — callers always check for None.
    """
    if not token or not CLERK_SECRET_KEY:
        return None
    try:
        import jwt

        header = jwt.get_unverified_header(token)
        kid    = header.get('kid')

        keys = _fetch_jwks()
        key_data = next((k for k in keys if k.get('kid') == kid), None)

        if key_data is None:
            # Unknown key-id — maybe Clerk just rotated. Force-refresh once.
            keys = _fetch_jwks(force=True)
            key_data = next((k for k in keys if k.get('kid') == kid), None)

        if key_data is None:
            return None

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)
        payload    = jwt.decode(
            token,
            public_key,
            algorithms=['RS256'],
            # Don't restrict audience — Clerk tokens don't always set 'aud'
            options={'verify_aud': False},
        )
        return payload.get('sub')

    except Exception:
        return None
