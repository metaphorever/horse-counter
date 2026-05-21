"""
poem_db.py - SQLite-backed poem storage for poet.horse.

Replaces the JSON-file storage in the legacy poem_store.py. Poems live in
the `poems` table; the public-facing identifier is `short_code` (used in
permalinks at /p/<short_code>).

Authorship model (mirrors db/schema.sql comments):
    * Logged-in poems       → author_user_id is set; display name + links
                              come from the user's profile.
    * Anonymous poems       → author_user_id is NULL; author_display_name and
                              author_link_url hold the per-poem attribution.
    * Legacy import poems   → anonymous, author_link_url synthesised from the
                              old submitter_tumblr handle.
"""

import json
import secrets
import time
from typing import Dict, List, Optional

from db.conn import get_db


SHORT_CODE_BYTES = 8  # secrets.token_urlsafe(8) -> ~11 chars, ~64 bits entropy


def _generate_short_code(conn) -> str:
    """Generate a unique short_code, retrying on collision."""
    for _ in range(8):
        code = secrets.token_urlsafe(SHORT_CODE_BYTES)
        # token_urlsafe can include '-' and '_' — fine for URLs, keep them
        exists = conn.execute(
            "SELECT 1 FROM poems WHERE short_code = ?", (code,)
        ).fetchone()
        if not exists:
            return code
    raise RuntimeError("Could not generate a unique short_code after 8 tries")


def _compute_counts(lines: List[List[Dict]]) -> Dict[str, int]:
    horse_count = sum(len(line) for line in lines)
    word_count  = sum(len(h['name'].split()) for line in lines for h in line)
    return {'horse_count': horse_count, 'word_count': word_count}


def _unique_horse_names(lines: List[List[Dict]]) -> List[str]:
    seen, result = set(), []
    for line in lines:
        for h in line:
            n = h.get('name', '')
            if n and n not in seen:
                seen.add(n)
                result.append(n)
    return result


def save_poem(
    lines:                 List[List[Dict]],
    title:                 str            = '',
    author_user_id:        Optional[int]  = None,
    author_display_name:   str            = '',
    author_link_url:       str            = '',
    status:                str            = 'submitted',
    short_code:            Optional[str]  = None,
    inspired_by_text:      str            = '',
    inspired_by_url:       str            = '',
) -> Dict:
    """
    Insert a poem and return its full row as a dict (including id and short_code).

    `status` is typically 'submitted' for public flow, 'published' for direct
    admin publish or for the legacy import. 'draft' for in-progress.

    `short_code` is generated automatically unless provided (used by the
    legacy import to preserve old IDs).

    `inspired_by_text` / `inspired_by_url` capture optional attribution to an
    existing work the poem riffs on / translates. Surfaced on the permalink
    as an "After ___" caption.
    """
    now = time.time()
    counts = _compute_counts(lines)
    lines_json = json.dumps(lines, ensure_ascii=False)

    with get_db() as conn:
        conn.execute("BEGIN")
        try:
            code = short_code or _generate_short_code(conn)
            cur = conn.execute(
                """INSERT INTO poems
                   (short_code, title, lines_json, status,
                    author_user_id, author_display_name, author_link_url,
                    inspired_by_text, inspired_by_url,
                    created_at, published_at, horse_count, word_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    code, title, lines_json, status,
                    author_user_id, author_display_name, author_link_url,
                    inspired_by_text, inspired_by_url,
                    now,
                    now if status == 'published' else None,
                    counts['horse_count'], counts['word_count'],
                ),
            )
            poem_id = cur.lastrowid
            # Index horse occurrences for fast "poems featuring X" lookups
            for name in _unique_horse_names(lines):
                conn.execute(
                    "INSERT OR IGNORE INTO horse_occurrences (poem_id, horse_name) VALUES (?, ?)",
                    (poem_id, name),
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return get_poem_by_id(poem_id)


def _row_to_poem(row) -> Dict:
    if row is None:
        return None
    d = dict(row)
    d['lines'] = json.loads(d.pop('lines_json'))
    return d


def get_poem_by_id(poem_id: int) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM poems WHERE id = ?", (poem_id,)
        ).fetchone()
    return _row_to_poem(row)


def get_poem_by_short_code(short_code: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM poems WHERE short_code = ?", (short_code,)
        ).fetchone()
    return _row_to_poem(row)


def update_poem_status(
    poem_id:    int,
    status:     str,
    published: bool = False,
) -> None:
    """Set status; if `published` is True also stamp published_at."""
    now = time.time()
    with get_db() as conn:
        if published:
            conn.execute(
                "UPDATE poems SET status = ?, published_at = ?, edited_at = ? WHERE id = ?",
                (status, now, now, poem_id),
            )
        else:
            conn.execute(
                "UPDATE poems SET status = ?, edited_at = ? WHERE id = ?",
                (status, now, poem_id),
            )


def get_poems_featuring_horse(horse_name: str, limit: int = 5) -> List[Dict]:
    """
    Return up to `limit` published poems that contain `horse_name`.
    Uses the horse_occurrences index for O(log n) lookup.
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.id, p.short_code, p.title, p.author_display_name,
                      p.author_user_id, p.horse_count, p.published_at
               FROM poems p
               JOIN horse_occurrences ho ON ho.poem_id = p.id
               WHERE ho.horse_name = ? AND p.status = 'published'
               ORDER BY p.published_at DESC
               LIMIT ?""",
            (horse_name, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def list_published(limit: int = 50, offset: int = 0) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM poems
               WHERE status = 'published'
               ORDER BY published_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    return [_row_to_poem(r) for r in rows]


_BROWSE_SORTS = {
    'newest':  'p.published_at DESC',
    'oldest':  'p.published_at ASC',
    'most':    'p.horse_count DESC, p.published_at DESC',
    'fewest':  'p.horse_count ASC, p.published_at DESC',
}


def _browse_where(tag_slug: Optional[str], attributed: bool) -> tuple:
    """Build the WHERE clause and params for browse queries."""
    clauses = ["p.status = 'published'"]
    params: List = []
    if tag_slug:
        clauses.append(
            "p.id IN (SELECT pt.poem_id FROM poem_tags pt "
            "JOIN tags t ON t.id = pt.tag_id "
            "WHERE t.slug = ? AND pt.status = 'approved')"
        )
        params.append(tag_slug)
    if attributed:
        clauses.append("p.inspired_by_text != ''")
    return " AND ".join(clauses), params


def browse_poems(
    sort:       str           = 'newest',
    tag_slug:   Optional[str] = None,
    page:       int           = 1,
    per_page:   int           = 20,
    attributed: bool          = False,
) -> List[Dict]:
    order = _BROWSE_SORTS.get(sort, _BROWSE_SORTS['newest'])
    where, params = _browse_where(tag_slug, attributed)
    offset = (max(1, page) - 1) * per_page
    sql = f"SELECT p.* FROM poems p WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?"
    with get_db() as conn:
        rows = conn.execute(sql, params + [per_page, offset]).fetchall()
    return [_row_to_poem(r) for r in rows]


def count_browse_poems(
    tag_slug:   Optional[str] = None,
    attributed: bool          = False,
) -> int:
    where, params = _browse_where(tag_slug, attributed)
    sql = f"SELECT COUNT(*) FROM poems p WHERE {where}"
    with get_db() as conn:
        return conn.execute(sql, params).fetchone()[0]


def get_poems_for_tag_slug(tag_slug: str, limit: int = 20) -> List[Dict]:
    """Return up to `limit` published poems that carry the given tag slug."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.id, p.short_code, p.title, p.author_display_name,
                      p.author_user_id, p.horse_count, p.published_at
                 FROM poems p
                 JOIN poem_tags pt ON pt.poem_id = p.id
                 JOIN tags t ON t.id = pt.tag_id
                WHERE t.slug = ? AND p.status = 'published' AND pt.status = 'approved'
                ORDER BY p.published_at DESC
                LIMIT ?""",
            (tag_slug, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_random_published() -> Optional[str]:
    """Return the short_code of a random published poem, or None if none exist."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT short_code FROM poems WHERE status='published' ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
    return row['short_code'] if row else None


def get_published_poems_by_user(user_id: int) -> List[Dict]:
    """All published poems by a user, newest first (for profile page)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, short_code, title, horse_count, published_at,
                      inspired_by_text, inspired_by_url
                 FROM poems
                WHERE author_user_id = ? AND status = 'published'
                ORDER BY published_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]
