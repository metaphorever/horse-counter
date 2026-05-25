"""
db/crosspost.py — Cross-post queue for publishing poems to Tumblr.

Each published poem is automatically added here with status='pending'.
Admin dispatches them from /admin/crosspost-queue.
"""

import json
import time
from typing import Optional

from db.conn import get_db
from poem_db import _enrich_lines


def enqueue_poem(poem_id: int) -> None:
    """Add a poem to the cross-post queue. No-op if already queued."""
    now = time.time()
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO crosspost_queue (poem_id, status, queued_at)
               VALUES (?, 'pending', ?)""",
            (poem_id, now),
        )


def get_pending() -> list[dict]:
    """Return pending queue items joined with poem data, oldest first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT cq.id AS cq_id, cq.queued_at,
                      p.id AS poem_id, p.short_code, p.title,
                      p.lines_json, p.horse_count, p.author_user_id,
                      p.author_display_name, p.author_link_url,
                      p.inspired_by_text, p.inspired_by_url,
                      p.published_at
                 FROM crosspost_queue cq
                 JOIN poems p ON p.id = cq.poem_id
                WHERE cq.status = 'pending'
                ORDER BY cq.queued_at ASC""",
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d['lines'] = json.loads(d.pop('lines_json'))
        _enrich_lines(d['lines'])
        items.append(d)
    return items


def mark_posted(cq_id: int) -> None:
    now = time.time()
    with get_db() as conn:
        conn.execute(
            "UPDATE crosspost_queue SET status='posted', posted_at=? WHERE id=?",
            (now, cq_id),
        )


def mark_skipped(cq_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE crosspost_queue SET status='skipped' WHERE id=?",
            (cq_id,),
        )
