"""
poem_submissions.py - SQLite-backed review queue for poem submissions.

A submission is a 1:1 link to a row in the `poems` table whose status is
'submitted'. When an admin approves, the poem flips to 'published' and the
submission row records who reviewed it and when.

This module is poem-only. The legacy url/text counter submissions still
live in submissions.py / submissions.json and are not affected by this.
"""

import time
from typing import Dict, List, Optional

from db.conn import get_db
from poem_db import get_poem_by_id, update_poem_status, _enrich_lines


def create_for_poem(poem_id: int) -> int:
    """Insert a pending submission for an already-saved poem. Returns submission id."""
    now = time.time()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO submissions (poem_id, status, submitted_at)
               VALUES (?, 'pending', ?)""",
            (poem_id, now),
        )
        return cur.lastrowid


def load_pending() -> List[Dict]:
    """Return pending submissions joined with their poems, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT s.id           AS submission_id,
                      s.status       AS submission_status,
                      s.submitted_at AS submitted_at,
                      p.*
               FROM submissions s
               JOIN poems p ON p.id = s.poem_id
               WHERE s.status = 'pending'
               ORDER BY s.submitted_at DESC""",
        ).fetchall()
    return [_join_row(r) for r in rows]


def load_submission(submission_id: int) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            """SELECT s.id           AS submission_id,
                      s.status       AS submission_status,
                      s.submitted_at AS submitted_at,
                      s.review_notes AS review_notes,
                      s.reviewed_by  AS reviewed_by,
                      s.reviewed_at  AS reviewed_at,
                      p.*
               FROM submissions s
               JOIN poems p ON p.id = s.poem_id
               WHERE s.id = ?""",
            (submission_id,),
        ).fetchone()
    return _join_row(row) if row else None


def approve(
    submission_id:    int,
    reviewer_user_id: Optional[int] = None,
    review_notes:     str           = '',
) -> Optional[Dict]:
    """Approve a submission and publish its poem. Returns the published poem."""
    sub = load_submission(submission_id)
    if not sub:
        return None
    now = time.time()
    with get_db() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(
                """UPDATE submissions
                   SET status = 'approved',
                       reviewed_by = ?,
                       reviewed_at = ?,
                       review_notes = ?
                   WHERE id = ?""",
                (reviewer_user_id, now, review_notes, submission_id),
            )
            conn.execute(
                "UPDATE poems SET status = 'published', published_at = ?, edited_at = ? WHERE id = ?",
                (now, now, sub['id']),
            )
            # Auto-approve any pending poem_tags — admin is making the editorial
            # call at publish time, implicitly approving the submitter's tag choices.
            conn.execute(
                "UPDATE poem_tags SET status = 'approved' WHERE poem_id = ? AND status = 'pending'",
                (sub['id'],),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return get_poem_by_id(sub['id'])


def reject(
    submission_id:    int,
    reviewer_user_id: Optional[int] = None,
    review_notes:     str           = '',
) -> None:
    """Reject a submission and mark its poem 'rejected'."""
    sub = load_submission(submission_id)
    if not sub:
        return
    now = time.time()
    with get_db() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(
                """UPDATE submissions
                   SET status = 'rejected',
                       reviewed_by = ?,
                       reviewed_at = ?,
                       review_notes = ?
                   WHERE id = ?""",
                (reviewer_user_id, now, review_notes, submission_id),
            )
            conn.execute(
                "UPDATE poems SET status = 'rejected', edited_at = ? WHERE id = ?",
                (now, sub['id']),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise


def _join_row(row) -> Dict:
    """
    The joined result has keys from both tables. We want a dict that:
      - Includes everything from the poem (id, short_code, title, lines, etc.)
      - Adds submission_id, submission_status, submitted_at, review_notes, etc.
      - Resolves the lines_json blob to a real list under 'lines'.
    """
    import json
    d = dict(row)
    d['lines'] = json.loads(d.pop('lines_json'))
    _enrich_lines(d['lines'])
    return d
