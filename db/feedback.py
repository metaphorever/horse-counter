"""
db/feedback.py — Bug report / feedback helpers for poet.horse.
"""

import time

from db.conn import get_db


def create_feedback(
    message: str,
    user_id=None,
    contact: str = '',
    user_agent: str = '',
) -> dict:
    now = time.time()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO feedback (user_id, contact, message, user_agent, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, contact[:200], message[:2000], user_agent[:300], now),
        )
        row = conn.execute(
            "SELECT * FROM feedback WHERE rowid = last_insert_rowid()"
        ).fetchone()
    return dict(row)


def set_github_url(feedback_id: int, url: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE feedback SET github_issue_url = ? WHERE id = ?",
            (url, feedback_id),
        )


def list_feedback(unread_only: bool = False) -> list:
    with get_db() as conn:
        sql = """
            SELECT f.*, u.slug AS user_slug, u.display_name AS user_display_name
              FROM feedback f
              LEFT JOIN users u ON u.id = f.user_id
            {where}
            ORDER BY f.created_at DESC
        """
        if unread_only:
            rows = conn.execute(
                sql.format(where="WHERE f.read_at IS NULL")
            ).fetchall()
        else:
            rows = conn.execute(sql.format(where="")).fetchall()
    return [dict(r) for r in rows]


def mark_read(feedback_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE feedback SET read_at = ? WHERE id = ?",
            (time.time(), feedback_id),
        )


def count_unread() -> int:
    with get_db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE read_at IS NULL"
        ).fetchone()[0]
