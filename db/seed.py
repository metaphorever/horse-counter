"""
db/seed.py — Idempotent column migrations and tag-taxonomy seeding.

Called from `init_db` on every boot. Safe to re-run: column adds are guarded
by table_info checks, tag seeding uses INSERT OR IGNORE keyed by slug.

Phase 1.3 introduced:
    * users.trust_level         — moderation scaffold (acted on in 1.13)
    * poems.inspired_by_text    — "After ___" attribution
    * poems.inspired_by_url     — optional source link
    * tag_categories            — seeded with four MVP categories
    * tags                      — seeded with curated baselines per category
"""

import time

from db.conn import get_db


_COLUMN_MIGRATIONS = [
    # (table, column, ddl-fragment)
    ('users', 'trust_level',      "TEXT NOT NULL DEFAULT 'pending'"),
    ('poems', 'inspired_by_text', "TEXT NOT NULL DEFAULT ''"),
    ('poems', 'inspired_by_url',  "TEXT NOT NULL DEFAULT ''"),
]


# Tag categories and their seed tags. Slugs are stable identifiers; labels
# are user-facing. Edit via admin tools (Phase 1.4) once that ships.
_CATEGORIES = [
    {
        'slug': 'poem-type', 'label': 'Poem Type',
        'behavior': 'single_select', 'sort_order': 10,
        'tags': [
            # "After / Translation" was briefly seeded here in 1.3 but pulled —
            # the relationship to an existing work is now a flag derived from
            # the presence of `poems.inspired_by_text`, not a tag. Browse-side
            # filter for it lands in 1.8.
            ('free-verse',  'Free verse'),
            ('haiku',       'Haiku'),
            ('limerick',    'Limerick'),
            ('sonnet',      'Sonnet'),
            ('couplet',     'Couplet'),
            ('ballad',      'Ballad'),
            ('ode',         'Ode'),
            ('prose-poem',  'Prose poem'),
            ('concrete',    'Concrete'),
            ('found',       'Found'),
            ('other',       'Other'),
        ],
    },
    {
        'slug': 'theme', 'label': 'Theme',
        'behavior': 'multi_select', 'sort_order': 20,
        'tags': [
            ('love',     'Love'),
            ('loss',     'Loss'),
            ('nature',   'Nature'),
            ('humor',    'Humor'),
            ('hope',     'Hope'),
            ('longing',  'Longing'),
            ('anger',    'Anger'),
            ('joy',      'Joy'),
            ('memory',   'Memory'),
            ('place',    'Place'),
            ('animals',  'Animals'),
            ('the-body', 'The body'),
            ('time',     'Time'),
            ('dreams',   'Dreams'),
            ('work',     'Work'),
            ('faith',    'Faith'),
            ('other',    'Other'),
        ],
    },
    {
        'slug': 'linguistic-features', 'label': 'Linguistic Features',
        'behavior': 'multi_select', 'sort_order': 30,
        'tags': [
            ('rhyming',        'Rhyming'),
            ('blank-verse',    'Blank verse'),
            ('metered',        'Metered'),
            ('alliterative',   'Alliterative'),
            ('repetition',     'Repetition'),
            ('internal-rhyme', 'Internal rhyme'),
        ],
    },
    {
        'slug': 'content-warnings', 'label': 'Content Warnings',
        'behavior': 'content_warning', 'sort_order': 40,
        'tags': [
            ('sex',                 'Sex'),
            ('drugs-and-alcohol',   'Drugs and alcohol'),
            ('violence',            'Violence'),
            ('self-harm',           'Self-harm'),
            ('death',               'Death'),
            ('slurs',               'Slurs'),
            ('mature-themes',       'Mature themes'),
        ],
    },
]


def _column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r['name'] == column for r in rows)


def apply_migrations() -> None:
    """Add missing columns. Idempotent."""
    with get_db() as conn:
        for table, column, ddl in _COLUMN_MIGRATIONS:
            if not _column_exists(conn, table, column):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def seed_tag_taxonomy() -> None:
    """Insert seed tag_categories + tags if missing. Keyed by slug; safe to re-run."""
    now = time.time()
    with get_db() as conn:
        conn.execute('BEGIN')
        for cat in _CATEGORIES:
            conn.execute(
                """INSERT OR IGNORE INTO tag_categories
                   (slug, label, behavior, sort_order, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (cat['slug'], cat['label'], cat['behavior'], cat['sort_order'], now),
            )
            cat_id = conn.execute(
                "SELECT id FROM tag_categories WHERE slug = ?", (cat['slug'],)
            ).fetchone()['id']
            for slug, label in cat['tags']:
                # Tag slugs are globally unique (the schema enforces this), so we
                # namespace per category by prefixing with the category slug.
                full_slug = f"{cat['slug']}:{slug}"
                conn.execute(
                    """INSERT OR IGNORE INTO tags
                       (slug, label, category_id, status, created_at)
                       VALUES (?, ?, ?, 'active', ?)""",
                    (full_slug, label, cat_id, now),
                )
        conn.execute('COMMIT')


_OBSOLETE_TAG_SLUGS = (
    # Briefly seeded in 1.3 then pulled — attribution to an existing work is a
    # flag derived from poems.inspired_by_text, not a tag.
    'poem-type:after',
)


def cleanup_obsolete_tags() -> None:
    """Remove tags we seeded then decided against. Idempotent — only acts on
    a known-deprecated slug list. Existing poem_tags references are cascaded."""
    with get_db() as conn:
        for slug in _OBSOLETE_TAG_SLUGS:
            row = conn.execute("SELECT id FROM tags WHERE slug = ?", (slug,)).fetchone()
            if not row:
                continue
            conn.execute('BEGIN')
            try:
                conn.execute("DELETE FROM poem_tags WHERE tag_id = ?", (row['id'],))
                conn.execute("DELETE FROM tags       WHERE id = ?",     (row['id'],))
                conn.execute('COMMIT')
            except Exception:
                conn.execute('ROLLBACK')
                raise


def run_all() -> None:
    apply_migrations()
    seed_tag_taxonomy()
    cleanup_obsolete_tags()
