"""
db/users.py — User table helpers for poet.horse.
"""

import re
import time

from db.conn import get_db

# URL-safe slug: 3–32 chars, lowercase alphanumeric + hyphens,
# no leading or trailing hyphen.
_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$')

_RESERVED_SLUGS = frozenset({
    'admin', 'api', 'static', 'p', 'u', 'auth',
    'sign-in', 'sign-out', 'setup-account',
    'terms', 'privacy', 'feed', 'recent', 'search',
    'count', 'poetry', 'submissions', 'queue',
    'login', 'logout', 'callback',
})


# ── Lookups ────────────────────────────────────────────────────────────────────

def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_clerk_id(clerk_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE clerk_id = ?', (clerk_id,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_slug(slug: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE slug = ? COLLATE NOCASE', (slug,)
        ).fetchone()
        return dict(row) if row else None


# ── Slug validation ────────────────────────────────────────────────────────────

def validate_slug(slug: str) -> str | None:
    """Return an error message string, or None if the slug is acceptable."""
    if not slug:
        return 'A slug is required.'
    if not _SLUG_RE.match(slug):
        return (
            'Slug must be 3–32 characters: lowercase letters, digits, and '
            'hyphens. No leading or trailing hyphens.'
        )
    if slug in _RESERVED_SLUGS:
        return f'"{slug}" is reserved — please choose something else.'
    return None


def slug_available(slug: str) -> bool:
    return validate_slug(slug) is None and get_user_by_slug(slug) is None


# ── Write ──────────────────────────────────────────────────────────────────────

def create_user(clerk_id: str, slug: str, display_name: str) -> dict:
    """Insert a new user row and return it as a dict. Raises on constraint violation."""
    now = time.time()
    with get_db() as conn:
        conn.execute('BEGIN')
        conn.execute(
            """INSERT INTO users (clerk_id, slug, display_name, role, joined_at)
               VALUES (?, ?, ?, 'user', ?)""",
            (clerk_id, slug.lower(), display_name, now),
        )
        row = conn.execute(
            'SELECT * FROM users WHERE clerk_id = ?', (clerk_id,)
        ).fetchone()
        conn.execute('COMMIT')
        return dict(row)
