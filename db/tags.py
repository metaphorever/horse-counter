"""
db/tags.py — Tag taxonomy helpers.

Read side: list_categories_with_tags() returns the structure the editor
populates the publish modal from.

Write side: apply_tags_to_poem(poem_id, tag_ids) inserts rows in poem_tags;
suggest_tag(category_id, label, user_id) creates a pending tag for admin
review (Phase 1.4 surface).

Validation:
    * Tag IDs are looked up; unknown / non-active IDs are silently dropped.
    * single_select categories: only the first tag in that category is kept.
    * content_warning + multi_select: all valid tags applied.
    * Duplicate tag IDs in input are deduped.
"""

import re
import time
from typing import Dict, Iterable, List, Optional

from db.conn import get_db


_SLUG_OK = re.compile(r'[^a-z0-9-]+')


def _slugify(label: str) -> str:
    s = label.lower().strip()
    s = re.sub(r'\s+', '-', s)
    s = _SLUG_OK.sub('', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s[:80] or 'tag'


def list_categories_with_tags(include_pending: bool = False) -> List[Dict]:
    """Return [{slug, label, behavior, sort_order, tags:[{id, slug, label}…]}, …].

    Tags within a category are sorted by label. Only `status='active'` tags
    are returned unless `include_pending=True`.
    """
    status_filter = "" if include_pending else "AND t.status = 'active'"
    sql = f"""
        SELECT c.id   AS cat_id,
               c.slug AS cat_slug,
               c.label AS cat_label,
               c.behavior,
               c.sort_order,
               t.id   AS tag_id,
               t.slug AS tag_slug,
               t.label AS tag_label,
               t.status AS tag_status
          FROM tag_categories c
          LEFT JOIN tags t ON t.category_id = c.id {status_filter}
         ORDER BY c.sort_order, c.id, t.label COLLATE NOCASE
    """
    with get_db() as conn:
        rows = conn.execute(sql).fetchall()

    cats: Dict[int, Dict] = {}
    for r in rows:
        cat = cats.setdefault(r['cat_id'], {
            'id':         r['cat_id'],
            'slug':       r['cat_slug'],
            'label':      r['cat_label'],
            'behavior':   r['behavior'],
            'sort_order': r['sort_order'],
            'tags':       [],
        })
        if r['tag_id'] is not None:
            cat['tags'].append({
                'id':     r['tag_id'],
                'slug':   r['tag_slug'],
                'label':  r['tag_label'],
                'status': r['tag_status'],
            })
    return [cats[k] for k in sorted(cats.keys(), key=lambda i: (cats[i]['sort_order'], i))]


def apply_tags_to_poem(
    poem_id:    int,
    tag_ids:    Iterable[int],
    applied_by: Optional[int] = None,
    status:     str           = 'approved',
) -> int:
    """
    Validate and insert poem_tags rows. Returns the number of rows inserted.

    * Drops unknown / non-active tag IDs.
    * For single_select categories, keeps only the first valid tag in that category.
    * Deduplicates input IDs.
    """
    wanted = [int(t) for t in tag_ids if t]
    if not wanted:
        return 0

    seen, deduped = set(), []
    for t in wanted:
        if t in seen:
            continue
        seen.add(t)
        deduped.append(t)

    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT t.id, t.category_id, c.behavior
                  FROM tags t JOIN tag_categories c ON t.category_id = c.id
                 WHERE t.status = 'active'
                   AND t.id IN ({','.join('?' * len(deduped))})""",
            deduped,
        ).fetchall()
        info = {r['id']: dict(r) for r in rows}

        used_single = set()
        ordered_valid = []
        for t in deduped:
            r = info.get(t)
            if not r:
                continue
            if r['behavior'] == 'single_select':
                if r['category_id'] in used_single:
                    continue
                used_single.add(r['category_id'])
            ordered_valid.append(t)

        if not ordered_valid:
            return 0

        now = time.time()
        conn.execute('BEGIN')
        try:
            inserted = 0
            for t in ordered_valid:
                cur = conn.execute(
                    """INSERT OR IGNORE INTO poem_tags
                       (poem_id, tag_id, applied_by, status, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (poem_id, t, applied_by, status, now),
                )
                inserted += cur.rowcount
            conn.execute('COMMIT')
            return inserted
        except Exception:
            conn.execute('ROLLBACK')
            raise


def suggest_tag(category_id: int, label: str, suggested_by: Optional[int]) -> Optional[int]:
    """Create a pending tag suggestion for admin review. Returns new tag id, or
    None if the category doesn't exist or the label collides with an existing
    tag in the same category (case-insensitive)."""
    label = (label or '').strip()
    if not label or len(label) > 60:
        return None

    with get_db() as conn:
        cat = conn.execute(
            "SELECT id, slug FROM tag_categories WHERE id = ?", (category_id,)
        ).fetchone()
        if not cat:
            return None

        existing = conn.execute(
            """SELECT 1 FROM tags
                WHERE category_id = ? AND label = ? COLLATE NOCASE""",
            (category_id, label),
        ).fetchone()
        if existing:
            return None

        # Build a unique slug under the category.
        base_slug = f"{cat['slug']}:{_slugify(label)}"
        slug = base_slug
        n = 2
        while conn.execute("SELECT 1 FROM tags WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{n}"
            n += 1

        cur = conn.execute(
            """INSERT INTO tags (slug, label, category_id, status, suggested_by, created_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (slug, label, category_id, suggested_by, time.time()),
        )
        return cur.lastrowid


def tags_for_poem(poem_id: int) -> List[Dict]:
    """Return approved poem_tags joined with the tag row, grouped by category
    (used by 1.5 permalink renderer)."""
    sql = """
        SELECT t.id, t.slug, t.label, t.status,
               c.id AS cat_id, c.slug AS cat_slug, c.label AS cat_label,
               c.behavior, c.sort_order
          FROM poem_tags pt
          JOIN tags t              ON t.id = pt.tag_id
          JOIN tag_categories c    ON c.id = t.category_id
         WHERE pt.poem_id = ? AND pt.status = 'approved'
         ORDER BY c.sort_order, c.id, t.label COLLATE NOCASE
    """
    with get_db() as conn:
        rows = conn.execute(sql, (poem_id,)).fetchall()
    return [dict(r) for r in rows]
