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

def create_user(clerk_id: str, slug: str, display_name: str, trust_score: int = 0) -> dict:
    """Insert a new user row and return it as a dict. Raises on constraint violation."""
    now = time.time()
    with get_db() as conn:
        conn.execute('BEGIN')
        conn.execute(
            """INSERT INTO users (clerk_id, slug, display_name, role, trust_score, joined_at)
               VALUES (?, ?, ?, 'user', ?, ?)""",
            (clerk_id, slug.lower(), display_name, trust_score, now),
        )
        row = conn.execute(
            'SELECT * FROM users WHERE clerk_id = ?', (clerk_id,)
        ).fetchone()
        conn.execute('COMMIT')
        return dict(row)


# ── Preferences (preferences_json) ────────────────────────────────────────────

def get_preferences(user_id: int) -> dict:
    """Return the parsed preferences_json dict (empty if missing or malformed)."""
    with get_db() as conn:
        row = conn.execute(
            'SELECT preferences_json FROM users WHERE id = ?', (user_id,)
        ).fetchone()
    if not row:
        return {}
    try:
        prefs = json.loads(row['preferences_json'] or '{}')
        return prefs if isinstance(prefs, dict) else {}
    except (TypeError, ValueError):
        return {}


def update_preferences(user_id: int, updates: dict) -> dict:
    """
    Shallow-merge `updates` into preferences_json. None values are dropped
    (i.e. won't overwrite existing keys with None). Returns the merged dict.
    """
    clean = {k: v for k, v in updates.items() if v is not None}
    current = get_preferences(user_id)
    current.update(clean)
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET preferences_json = ? WHERE id = ?',
            (json.dumps(current, ensure_ascii=False), user_id),
        )
    return current


# ── Profile editing (Phase 1.15) ──────────────────────────────────────────────

def update_profile(user_id: int, display_name: str, links: list) -> None:
    """Update display_name and links_json for a user."""
    display_name = (display_name or '').strip()[:80]
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET display_name = ?, links_json = ? WHERE id = ?',
            (display_name, json.dumps(links, ensure_ascii=False), user_id),
        )


def set_bio_poem(user_id: int, poem_id) -> None:
    """Set or clear the profile bio poem (pass None to clear)."""
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET bio_poem_id = ? WHERE id = ?',
            (poem_id, user_id),
        )


def update_trust_score(user_id: int, delta: int) -> int:
    """Add delta (+1 or -1) to user's trust_score. Returns the new score."""
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET trust_score = trust_score + ? WHERE id = ?',
            (delta, user_id),
        )
        row = conn.execute('SELECT trust_score FROM users WHERE id = ?', (user_id,)).fetchone()
    return row['trust_score'] if row else 0


def set_trust_score(user_id: int, score: int) -> None:
    """Manually override a user's trust_score."""
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET trust_score = ? WHERE id = ?',
            (score, user_id),
        )


def suspend_user(user_id: int) -> None:
    import time
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET suspended_at = ? WHERE id = ?',
            (time.time(), user_id),
        )


def unsuspend_user(user_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            'UPDATE users SET suspended_at = NULL WHERE id = ?',
            (user_id,),
        )


def delete_user(user_id: int) -> None:
    """Delete a user row. FK cascades handle drafts/pasture/saved collections.
    poems.author_user_id is ON DELETE SET NULL — poems orphan to anonymous."""
    with get_db() as conn:
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))


def get_all_users(limit: int = 200) -> list:
    """Return all users ordered by join date, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM users ORDER BY joined_at DESC LIMIT ?', (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_published_poems(user_id: int) -> list:
    """Return all published poems by this user, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, short_code, title, horse_count, published_at
                 FROM poems
                WHERE author_user_id = ? AND status = 'published'
                ORDER BY published_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_user_poems_for_bio_picker(user_id: int) -> list:
    """Return published + submitted poems for the bio picker, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, short_code, title, horse_count, status, created_at
                 FROM poems
                WHERE author_user_id = ? AND status IN ('published', 'submitted')
                ORDER BY created_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]
