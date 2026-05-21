"""
db/reports.py — Report queue helpers (Phase 1.14).

Reports let users flag poems for admin review. Only poem reports are
implemented in Phase 1.14; the schema supports more target_types.
"""

import time

from db.conn import get_db


def create_report(
    target_type: str,
    target_id: int,
    reason: str,
    reporter_user_id=None,
    reporter_ip: str = '',
) -> dict:
    """Insert a report row and return it as a dict."""
    now = time.time()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO reports
               (target_type, target_id, reporter_user_id, reporter_ip, reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (target_type, target_id, reporter_user_id, reporter_ip, reason[:500], now),
        )
        row = conn.execute(
            "SELECT * FROM reports WHERE rowid = last_insert_rowid()"
        ).fetchone()
    return dict(row)


def list_reports(status: str = 'pending') -> list:
    """Return reports with poem info joined, filtered by status."""
    with get_db() as conn:
        if status == 'all':
            rows = conn.execute(
                """SELECT r.*,
                          p.short_code AS poem_short_code,
                          p.title      AS poem_title,
                          u.display_name AS reporter_name,
                          u.slug         AS reporter_slug
                     FROM reports r
                     LEFT JOIN poems p ON p.id = r.target_id AND r.target_type = 'poem'
                     LEFT JOIN users u ON u.id = r.reporter_user_id
                    ORDER BY r.created_at DESC""",
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT r.*,
                          p.short_code AS poem_short_code,
                          p.title      AS poem_title,
                          u.display_name AS reporter_name,
                          u.slug         AS reporter_slug
                     FROM reports r
                     LEFT JOIN poems p ON p.id = r.target_id AND r.target_type = 'poem'
                     LEFT JOIN users u ON u.id = r.reporter_user_id
                    WHERE r.status = ?
                    ORDER BY r.created_at DESC""",
                (status,),
            ).fetchall()
    return [dict(r) for r in rows]


def resolve_report(report_id: int, action: str, resolver_id: int) -> bool:
    """Set status to 'actioned' or 'dismissed'. Returns True if a row was updated."""
    if action not in ('actioned', 'dismissed'):
        return False
    now = time.time()
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE reports SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
            (action, now, resolver_id, report_id),
        )
    return cur.rowcount > 0
