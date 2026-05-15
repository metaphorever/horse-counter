"""
db/users.py — User table helpers for poet.horse.
"""

import json
import re
import time

from db.conn import get_db

# URL-safe slug: 3–32 chars, lowercase alphanumeric + hyphens,
# no leading or trailing hyphen.
_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$')

_RESERVED_SLUGS = frozenset({
    'admin', 'api', 'static', 'p', 'u', 'auth', 'me',
    'sign-in', 'sign-out', 'setup-account',
    'terms', 'privacy', 'data-deletion', 'feed', 'recent', 'search',
    'count', 'poetry', 'write', 'pasture', 'browse',
    'featured', 'random', 'submissions', 'queue', 'support',
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


# ── Preferences ────────────────────────────────────────────────────────────────

def merge_preferences(user_id: int, new_prefs: dict, only_if_blank: bool = True) -> dict:
    """
    Merge `new_prefs` into users.preferences_json. When `only_if_blank` is set
    (the default — used by the localStorage sync flow), existing keys are not
    overwritten. Returns the resulting preferences dict.
    """
    with get_db() as conn:
        row = conn.execute(
            'SELECT preferences_json FROM users WHERE id = ?', (user_id,),
        ).fetchone()
        if row is None:
            return {}
        try:
            current = json.loads(row['preferences_json'] or '{}')
        except (TypeError, ValueError):
            current = {}
        for k, v in new_prefs.items():
            if v in (None, ''):
                continue
            if only_if_blank and k in current and current[k] not in (None, ''):
                continue
            current[k] = v
        conn.execute(
            'UPDATE users SET preferences_json = ? WHERE id = ?',
            (json.dumps(current), user_id),
        )
        return current


# ── Per-user stable (server-side) ──────────────────────────────────────────────

def load_stable_for_user(user_id: int) -> list[dict]:
    """Return the user's stable as a list of {name, display, url, remaining} dicts."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT name, display, url, remaining
                 FROM stable_horses
                WHERE user_id = ?
             ORDER BY added_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def merge_stable_for_user(user_id: int, horses: list[dict]) -> int:
    """
    Insert each horse into stable_horses if not already present for this user.
    Returns the number of newly-inserted rows.
    """
    if not horses:
        return 0
    now = time.time()
    inserted = 0
    with get_db() as conn:
        conn.execute('BEGIN')
        for h in horses:
            name    = (h.get('name')    or '').strip()
            display = (h.get('display') or name).strip()
            url     = (h.get('url')     or '').strip()
            try:
                remaining = int(h.get('remaining') or 1)
            except (TypeError, ValueError):
                remaining = 1
            if not name:
                continue
            cur = conn.execute(
                """INSERT OR IGNORE INTO stable_horses
                       (user_id, name, display, url, remaining, added_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, name, display, url, max(1, remaining), now),
            )
            inserted += cur.rowcount or 0
        conn.execute('COMMIT')
    return inserted
