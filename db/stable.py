"""
db/stable.py — Per-user stable_horses helpers.

The composition working area for logged-in users. Anonymous users keep their
stable in localStorage; on first login it is bulk-merged here by /me/sync.
"""

import time

from db.conn import get_db


def list_stable_horses(user_id: int) -> list[dict]:
    """Return this user's stable, newest-first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT name, display, url, remaining, added_at
                 FROM stable_horses
                WHERE user_id = ?
                ORDER BY added_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def remove_stable_horse(user_id: int, name: str) -> None:
    with get_db() as conn:
        conn.execute(
            "DELETE FROM stable_horses WHERE user_id = ? AND name = ?",
            (user_id, name),
        )
        conn.commit()


def clear_stable_horses(user_id: int) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM stable_horses WHERE user_id = ?", (user_id,))
        conn.commit()


def bulk_add_stable_horses(user_id: int, horses: list[dict]) -> int:
    """
    Insert horses for the given user, skipping any whose name already exists
    for them. Returns the number of newly inserted rows.

    Each horse must have keys: name, display, url. `remaining` is optional
    (defaults to 1).
    """
    now = time.time()
    inserted = 0
    with get_db() as conn:
        conn.execute('BEGIN')
        for h in horses:
            name    = (h.get('name') or '').strip()
            display = (h.get('display') or name).strip()
            url     = (h.get('url') or '').strip()
            if not name:
                continue
            remaining = int(h.get('remaining') or 1)
            cur = conn.execute(
                """INSERT OR IGNORE INTO stable_horses
                   (user_id, name, display, url, remaining, added_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, name, display, url, remaining, now),
            )
            inserted += cur.rowcount
        conn.execute('COMMIT')
    return inserted
