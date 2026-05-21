"""
db/drafts.py — Per-user SQLite draft CRUD helpers.

Distinct from queue_handler.py save_draft/load_draft which are ephemeral
file-based drafts for the Tumblr submission queue (Phase 1.13). These are
persistent user-named drafts introduced in Phase 1.27.
"""

import json
import time

from db.conn import get_db


def list_user_drafts(user_id: int) -> list[dict]:
    """Return all drafts for this user, newest-updated first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, title, lines_json, stable_json, updated_at, created_at
               FROM drafts
               WHERE user_id = ?
               ORDER BY updated_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_user_draft(draft_id: int, user_id: int) -> dict | None:
    """Return a single draft, or None if not found / wrong user."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def save_user_draft(
    user_id: int,
    draft_id: int | None,
    title: str,
    lines_json: str,
    stable_json: str,
    submitter_name: str = '',
    submitter_tumblr: str = '',
    inspired_by_text: str = '',
    inspired_by_url: str = '',
    tag_ids_json: str = '[]',
) -> dict:
    """Create or update a draft. Returns the saved row as a dict.

    If draft_id is provided and owned by user_id, updates in place.
    Otherwise creates a new draft. Untitled drafts are auto-named 'Poem #N'.
    """
    now = time.time()
    with get_db() as conn:
        if draft_id:
            row = conn.execute(
                "SELECT id FROM drafts WHERE id = ? AND user_id = ?",
                (draft_id, user_id),
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE drafts
                       SET title=?, lines_json=?, stable_json=?,
                           submitter_name=?, submitter_tumblr=?,
                           inspired_by_text=?, inspired_by_url=?,
                           tag_ids_json=?, updated_at=?
                       WHERE id = ? AND user_id = ?""",
                    (title, lines_json, stable_json,
                     submitter_name, submitter_tumblr,
                     inspired_by_text, inspired_by_url,
                     tag_ids_json, now,
                     draft_id, user_id),
                )
                conn.commit()
                return get_user_draft(draft_id, user_id)

        # New draft — auto-name if no title given
        if not title:
            title = "untitled"

        cur = conn.execute(
            """INSERT INTO drafts
               (user_id, title, lines_json, stable_json,
                submitter_name, submitter_tumblr,
                inspired_by_text, inspired_by_url,
                tag_ids_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, title, lines_json, stable_json,
             submitter_name, submitter_tumblr,
             inspired_by_text, inspired_by_url,
             tag_ids_json, now, now),
        )
        conn.commit()
        return get_user_draft(cur.lastrowid, user_id)


def add_horse_to_draft_stable(
    draft_id: int, user_id: int, name: str, display: str, url: str
) -> bool:
    """Append a horse to a draft's stable_json. Returns False if already present
    or draft not found."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, stable_json FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        ).fetchone()
        if not row:
            return False
        stable = json.loads(row['stable_json'] or '[]')
        if any(h.get('name') == name for h in stable):
            return False
        stable.append({'name': name, 'display': display, 'url': url, 'remaining': 1})
        conn.execute(
            "UPDATE drafts SET stable_json = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (json.dumps(stable), time.time(), draft_id, user_id),
        )
        conn.commit()
        return True


def delete_user_draft(draft_id: int, user_id: int) -> bool:
    """Delete a draft. Returns True if a row was deleted."""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
