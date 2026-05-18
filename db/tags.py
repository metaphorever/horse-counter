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


def _build_categories(rows) -> List[Dict]:
    cats: Dict[int, Dict] = {}
    for r in rows:
        cat = cats.setdefault(r['cat_id'], {
            'id':         r['cat_id'],
            'slug':       r['cat_slug'],
            'label':      r['cat_label'],
            'behavior':   r['behavior'],
            'sort_order': r['sort_order'],
            'admin_only': bool(r['admin_only']),
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


def _cat_query(admin_only_filter: Optional[str], include_pending: bool) -> str:
    status_filter = "" if include_pending else "AND t.status = 'active'"
    admin_filter  = "" if admin_only_filter is None else f"AND c.admin_only = {admin_only_filter}"
    return f"""
        SELECT c.id       AS cat_id,
               c.slug     AS cat_slug,
               c.label    AS cat_label,
               c.behavior,
               c.sort_order,
               c.admin_only,
               t.id       AS tag_id,
               t.slug     AS tag_slug,
               t.label    AS tag_label,
               t.status   AS tag_status
          FROM tag_categories c
          LEFT JOIN tags t ON t.category_id = c.id {status_filter}
         WHERE 1=1 {admin_filter}
         ORDER BY c.sort_order, c.id, t.label COLLATE NOCASE
    """


def list_categories_with_tags(include_pending: bool = False) -> List[Dict]:
    """Public-facing: only non-admin-only categories."""
    with get_db() as conn:
        rows = conn.execute(_cat_query('0', include_pending)).fetchall()
    return _build_categories(rows)


def list_all_categories_with_tags(include_pending: bool = False) -> List[Dict]:
    """Admin-facing: all categories, both public and admin-only."""
    with get_db() as conn:
        rows = conn.execute(_cat_query(None, include_pending)).fetchall()
    return _build_categories(rows)


def list_admin_only_categories_with_tags(include_pending: bool = False) -> List[Dict]:
    """Admin-facing: only admin-only categories."""
    with get_db() as conn:
        rows = conn.execute(_cat_query('1', include_pending)).fetchall()
    return _build_categories(rows)


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
    """Return approved poem_tags joined with tag + category rows.

    Includes c.admin_only so callers can partition public vs admin-only tags.
    """
    sql = """
        SELECT t.id, t.slug, t.label, t.status,
               c.id AS cat_id, c.slug AS cat_slug, c.label AS cat_label,
               c.behavior, c.sort_order, c.admin_only
          FROM poem_tags pt
          JOIN tags t              ON t.id = pt.tag_id
          JOIN tag_categories c    ON c.id = t.category_id
         WHERE pt.poem_id = ? AND pt.status = 'approved'
         ORDER BY c.sort_order, c.id, t.label COLLATE NOCASE
    """
    with get_db() as conn:
        rows = conn.execute(sql, (poem_id,)).fetchall()
    return [dict(r) for r in rows]


def update_poem_tags(
    poem_id:    int,
    tag_ids:    Iterable[int],
    applied_by: Optional[int] = None,
) -> int:
    """Replace all approved tags on a poem with the provided set.

    Preserves pending/rejected poem_tags rows (those belong to the moderation
    flow). Returns the number of approved rows inserted.
    """
    wanted = [int(t) for t in tag_ids if t]
    with get_db() as conn:
        conn.execute('BEGIN')
        try:
            conn.execute(
                "DELETE FROM poem_tags WHERE poem_id = ? AND status = 'approved'",
                (poem_id,),
            )
            conn.execute('COMMIT')
        except Exception:
            conn.execute('ROLLBACK')
            raise

    if not wanted:
        return 0
    return apply_tags_to_poem(poem_id, wanted, applied_by=applied_by, status='approved')


def create_tag_category(
    label:      str,
    behavior:   str  = 'multi_select',
    admin_only: bool = False,
    sort_order: int  = 0,
) -> Optional[int]:
    """Create a new tag category. Returns new id, or None if slug collides."""
    label = (label or '').strip()
    if not label or len(label) > 60:
        return None
    slug = _slugify(label)
    now  = time.time()
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM tag_categories WHERE slug = ? COLLATE NOCASE", (slug,)).fetchone():
            return None
        cur = conn.execute(
            "INSERT INTO tag_categories (slug, label, behavior, sort_order, admin_only, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (slug, label, behavior, sort_order, int(admin_only), now),
        )
        return cur.lastrowid


def create_tag(category_id: int, label: str, admin_created: bool = True) -> Optional[int]:
    """Create an active tag in the given category. Returns new id, or None on collision."""
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
            "SELECT 1 FROM tags WHERE category_id = ? AND label = ? COLLATE NOCASE",
            (category_id, label),
        ).fetchone()
        if existing:
            return None
        base_slug = f"{cat['slug']}:{_slugify(label)}"
        slug = base_slug
        n = 2
        while conn.execute("SELECT 1 FROM tags WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{n}"
            n += 1
        cur = conn.execute(
            "INSERT INTO tags (slug, label, category_id, status, created_at) VALUES (?, ?, ?, 'active', ?)",
            (slug, label, category_id, time.time()),
        )
        return cur.lastrowid


# ── Featured sections ─────────────────────────────────────────────────────────

def list_featured_sections() -> List[Dict]:
    """All active featured sections ordered by sort_order, with tag info."""
    sql = """
        SELECT fs.id, fs.tag_id, fs.label AS section_label, fs.sort_order, fs.active,
               t.label AS tag_label, t.slug AS tag_slug,
               c.admin_only
          FROM featured_sections fs
          JOIN tags t ON t.id = fs.tag_id
          JOIN tag_categories c ON c.id = t.category_id
         WHERE fs.active = 1
         ORDER BY fs.sort_order, fs.id
    """
    with get_db() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def list_all_featured_sections() -> List[Dict]:
    """All featured sections (active and inactive) for admin management."""
    sql = """
        SELECT fs.id, fs.tag_id, fs.label AS section_label, fs.sort_order, fs.active,
               t.label AS tag_label, t.slug AS tag_slug,
               c.admin_only
          FROM featured_sections fs
          JOIN tags t ON t.id = fs.tag_id
          JOIN tag_categories c ON c.id = t.category_id
         ORDER BY fs.sort_order, fs.id
    """
    with get_db() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def add_featured_section(
    tag_id:     int,
    label:      str = '',
    sort_order: int = 0,
) -> Optional[int]:
    """Add a tag as a featured section. Returns new id, or None if already present."""
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM featured_sections WHERE tag_id = ?", (tag_id,)).fetchone():
            return None
        cur = conn.execute(
            "INSERT INTO featured_sections (tag_id, label, sort_order, active, created_at) VALUES (?, ?, ?, 1, ?)",
            (tag_id, (label or '').strip(), sort_order, time.time()),
        )
        return cur.lastrowid


def update_featured_section(
    section_id: int,
    label:      Optional[str] = None,
    sort_order: Optional[int] = None,
    active:     Optional[bool] = None,
) -> bool:
    """Update one or more fields on a featured section. Returns True if found."""
    sets, params = [], []
    if label is not None:
        sets.append("label = ?");      params.append(label.strip())
    if sort_order is not None:
        sets.append("sort_order = ?"); params.append(sort_order)
    if active is not None:
        sets.append("active = ?");     params.append(int(active))
    if not sets:
        return False
    params.append(section_id)
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE featured_sections SET {', '.join(sets)} WHERE id = ?", params
        )
        return cur.rowcount > 0


def remove_featured_section(section_id: int) -> bool:
    """Delete a featured section. Returns True if found."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM featured_sections WHERE id = ?", (section_id,))
        return cur.rowcount > 0
