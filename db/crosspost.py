"""
db/crosspost.py — Multi-target cross-post queue for published poems.

Each published poem is auto-enqueued. Admin dispatches from
/admin/crosspost-queue with a single "Crosspost" action that fires every
connected platform live. Result is tracked per platform so a partial failure is
retryable:

    tumblr_status / bluesky_status:  NULL (fresh) → posted / failed / skipped

An item stays pending until BOTH platforms are resolved (posted or skipped);
a 'failed' platform keeps the item pending so re-dispatch retries just that one.
The legacy `status` / `posted_at` columns are left in place but unused.
"""

import json
import time

from db.conn import get_db
from db.tags import tags_for_poem
from poem_db import _enrich_lines

PLATFORMS = ('tumblr', 'bluesky')
_STATUSES = ('posted', 'failed', 'skipped')
_RESOLVED = ('posted', 'skipped')


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
    """Return queue items not yet resolved on both platforms, oldest first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT cq.id AS cq_id, cq.queued_at,
                      cq.tumblr_status, cq.bluesky_status,
                      p.id AS poem_id, p.short_code, p.title,
                      p.lines_json, p.horse_count, p.author_user_id,
                      p.author_display_name, p.author_link_url,
                      p.inspired_by_text, p.inspired_by_url,
                      p.published_at
                 FROM crosspost_queue cq
                 JOIN poems p ON p.id = cq.poem_id
                WHERE NOT ( COALESCE(cq.tumblr_status, '')  IN ('posted', 'skipped')
                       AND  COALESCE(cq.bluesky_status, '') IN ('posted', 'skipped') )
                ORDER BY cq.queued_at ASC""",
        ).fetchall()
    items = []
    for r in rows:
        d = dict(r)
        d['lines'] = json.loads(d.pop('lines_json'))
        _enrich_lines(d['lines'])
        # Poem's approved tags — feeds the Bluesky CW self-label (content-warnings
        # rows) and the Tumblr site-tag splice (all non-admin rows). Phase 2.3.
        d['tags'] = tags_for_poem(d['poem_id'])
        items.append(d)
    return items


def mark_platform(cq_id: int, platform: str, status: str) -> None:
    """Record a per-platform dispatch result. Column name is whitelisted."""
    if platform not in PLATFORMS:
        raise ValueError(f'unknown platform: {platform}')
    if status not in _STATUSES:
        raise ValueError(f'unknown status: {status}')
    col = f'{platform}_status'  # safe: platform validated against PLATFORMS
    with get_db() as conn:
        conn.execute(
            f"UPDATE crosspost_queue SET {col} = ? WHERE id = ?",
            (status, cq_id),
        )


def skip(cq_id: int) -> None:
    """Resolve an item out of the queue without posting (both platforms skipped)."""
    with get_db() as conn:
        conn.execute(
            "UPDATE crosspost_queue SET tumblr_status='skipped', bluesky_status='skipped'"
            " WHERE id = ?",
            (cq_id,),
        )
