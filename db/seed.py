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

Pre-1.8 fix: dedup_tag_taxonomy() collapses duplicate taxonomy rows that
accumulated on DBs created before tag_categories.slug / tags.slug had a UNIQUE
constraint, then enforces the constraint via named indexes going forward.
"""

import time

from db.conn import get_db


_COLUMN_MIGRATIONS = [
    # (table, column, ddl-fragment)
    ('users',          'trust_level',  "TEXT NOT NULL DEFAULT 'pending'"),
    ('poems',          'inspired_by_text', "TEXT NOT NULL DEFAULT ''"),
    ('poems',          'inspired_by_url',  "TEXT NOT NULL DEFAULT ''"),
    ('tag_categories', 'admin_only',   "INTEGER NOT NULL DEFAULT 0"),
    # Phase 1.27 — draft metadata (draft-centric stable model)
    ('drafts', 'stable_json',       "TEXT NOT NULL DEFAULT '[]'"),
    ('drafts', 'submitter_name',    "TEXT NOT NULL DEFAULT ''"),
    ('drafts', 'submitter_tumblr',  "TEXT NOT NULL DEFAULT ''"),
    ('drafts', 'inspired_by_text',  "TEXT NOT NULL DEFAULT ''"),
    ('drafts', 'inspired_by_url',   "TEXT NOT NULL DEFAULT ''"),
    ('drafts', 'tag_ids_json',      "TEXT NOT NULL DEFAULT '[]'"),
    ('drafts', 'created_at',        "REAL NOT NULL DEFAULT 0"),
    # Phase 1.15 — bio poem on user profile (FK omitted; SQLite ALTER TABLE doesn't support it)
    ('users', 'bio_poem_id', "INTEGER"),
    # Pre-1.13 polish — attribution mode stored on draft
    ('drafts', 'post_as', "TEXT NOT NULL DEFAULT 'account'"),
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


def dedup_tag_taxonomy() -> None:
    """Collapse duplicate tag_categories / tags rows and enforce UNIQUE on slug.

    Root cause: if the production DB was created from a schema.sql version that
    lacked the UNIQUE constraint on these columns, INSERT OR IGNORE in
    seed_tag_taxonomy() is a no-op (nothing to ignore), so every boot inserts
    fresh copies of the full taxonomy. This runs before seeding to repair that
    state and then creates named UNIQUE indexes so the constraint holds on future
    boots regardless of how the table was originally created.
    """
    with get_db() as conn:
        conn.execute('BEGIN')
        try:
            # --- tag_categories ---
            dup_cats = conn.execute("""
                SELECT slug, MIN(id) AS keep_id
                FROM tag_categories
                GROUP BY slug COLLATE NOCASE
                HAVING COUNT(*) > 1
            """).fetchall()
            for cat in dup_cats:
                # Reparent tags from all duplicate category rows to the canonical one.
                conn.execute(
                    "UPDATE tags SET category_id = ? WHERE category_id IN "
                    "(SELECT id FROM tag_categories WHERE slug = ? COLLATE NOCASE AND id != ?)",
                    (cat['keep_id'], cat['slug'], cat['keep_id']),
                )
                conn.execute(
                    "DELETE FROM tag_categories WHERE slug = ? COLLATE NOCASE AND id != ?",
                    (cat['slug'], cat['keep_id']),
                )

            # --- tags ---
            dup_tags = conn.execute("""
                SELECT slug, MIN(id) AS keep_id
                FROM tags
                GROUP BY slug COLLATE NOCASE
                HAVING COUNT(*) > 1
            """).fetchall()
            for tag in dup_tags:
                # Drop poem_tags rows that would create a PK conflict after the remap
                # (poem already tagged with the canonical tag id).
                conn.execute(
                    "DELETE FROM poem_tags "
                    "WHERE tag_id != ? "
                    "  AND tag_id IN (SELECT id FROM tags WHERE slug = ? COLLATE NOCASE) "
                    "  AND poem_id IN (SELECT poem_id FROM poem_tags WHERE tag_id = ?)",
                    (tag['keep_id'], tag['slug'], tag['keep_id']),
                )
                conn.execute(
                    "UPDATE poem_tags SET tag_id = ? WHERE tag_id IN "
                    "(SELECT id FROM tags WHERE slug = ? COLLATE NOCASE AND id != ?)",
                    (tag['keep_id'], tag['slug'], tag['keep_id']),
                )
                conn.execute(
                    "DELETE FROM tags WHERE slug = ? COLLATE NOCASE AND id != ?",
                    (tag['slug'], tag['keep_id']),
                )

            # Enforce uniqueness via named indexes. Safe if the column-level UNIQUE
            # autoindex already exists — IF NOT EXISTS checks the index name, not the
            # column, so this is additive and harmless when the constraint is already
            # present. Must run after dedup or it will fail on remaining conflicts.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_tag_categories_slug "
                "ON tag_categories(slug COLLATE NOCASE)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_tags_slug "
                "ON tags(slug COLLATE NOCASE)"
            )
            conn.execute('COMMIT')
        except Exception:
            conn.execute('ROLLBACK')
            raise


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
    dedup_tag_taxonomy()   # must run before seed — cleans up pre-constraint duplicates
    seed_tag_taxonomy()
    cleanup_obsolete_tags()
