"""
db/admin_settings.py — Key/value store for admin-configurable settings.

Phase 1.13.1: auto_post_threshold (int)
    trust_score a user must meet to bypass the submission queue.
    0 = open posting; NULL/'' = feature disabled (everyone queues).

anon_auto_post / pseudo_auto_post (bool, stored as '1' / '')
    Whether fully-anonymous or pseudonymous posts bypass the queue.
    No trust score applies — it's a simple on/off per post_as type.

new_user_trust_score (int, default 0)
    trust_score assigned to new accounts at registration.
"""

import time

from db.conn import get_db


def get_setting(key: str, default=None):
    """Return the raw string value for key, or default if not set."""
    with get_db() as conn:
        row = conn.execute(
            'SELECT value FROM admin_settings WHERE key = ?', (key,)
        ).fetchone()
    if row is None:
        return default
    return row['value']


def set_setting(key: str, value: str) -> None:
    """Upsert a setting value."""
    now = time.time()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO admin_settings (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, value, now),
        )


def get_anon_auto_post() -> bool:
    """Return True if fully-anonymous posts bypass the submission queue."""
    return get_setting('anon_auto_post', '') == '1'


def get_pseudo_auto_post() -> bool:
    """Return True if pseudonymous posts bypass the submission queue."""
    return get_setting('pseudo_auto_post', '') == '1'


def get_new_user_trust_score() -> int:
    """Return the trust_score assigned to new accounts at registration. Default 0."""
    raw = get_setting('new_user_trust_score', '0')
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def get_auto_post_threshold() -> int | None:
    """
    Return the auto_post_threshold as an int, or None if disabled.
    Empty string or missing → disabled (no bypass).
    """
    raw = get_setting('auto_post_threshold', '')
    if raw == '' or raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
