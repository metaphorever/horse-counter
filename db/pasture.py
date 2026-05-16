"""
db/pasture.py — Per-user pasture_horses helpers.

The long-term collection of horses a user has explicitly saved to "My Pasture"
from the editor or a horse popover. Distinct from stable_horses (the current
poem's working pool) and from any future saved_horses (sentiment / blue-ribbon).

Anonymous users do not have a pasture — the UI prompts them to sign in.
"""

import time

from db.conn import get_db


def list_pasture_horses(user_id: int) -> list[dict]:
    """Return this user's pasture, newest-first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT name, display, url, added_at
                 FROM pasture_horses
                WHERE user_id = ?
                ORDER BY added_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_to_pasture(user_id: int, name: str, display: str, url: str) -> bool:
    """
    Insert one horse into the user's pasture. Returns True if a new row was
    inserted, False if the horse was already there.
    """
    name    = (name    or '').strip()
    display = (display or name).strip()
    url     = (url     or '').strip()
    if not name:
        return False
    with get_db() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO pasture_horses
               (user_id, name, display, url, added_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, name, display, url, time.time()),
        )
        return cur.rowcount > 0
