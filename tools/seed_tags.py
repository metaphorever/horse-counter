"""
tools/seed_tags.py - Seed the MVP tag categories and tags.

Idempotent: existing tags/categories are skipped, not overwritten.
Run via tools.init_db --seed-tags or directly:

    python -m tools.seed_tags
"""

import time
from typing import Dict

from db.conn import get_db


# Owner-editable. Order in the lists is the display order in the editor.
SEED = [
    {
        'slug':     'poem-type',
        'label':    'Poem Type',
        'behavior': 'single_select',
        'tags': [
            ('free-verse',  'Free verse'),
            ('haiku',       'Haiku'),
            ('limerick',    'Limerick'),
            ('sonnet',      'Sonnet'),
            ('couplet',     'Couplet'),
            ('ballad',      'Ballad'),
            ('ode',         'Ode'),
            ('prose-poem',  'Prose poem'),
            ('concrete',    'Concrete'),
            ('found',       'Found poetry'),
            ('other',       'Other'),
        ],
    },
    {
        'slug':     'theme',
        'label':    'Theme',
        'behavior': 'multi_select',
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
        'slug':     'content-warning',
        'label':    'Content Warnings',
        'behavior': 'content_warning',
        'tags': [
            ('cw-sex',          'Sex'),
            ('cw-drugs',        'Drugs and alcohol'),
            ('cw-violence',     'Violence'),
            ('cw-self-harm',    'Self-harm'),
            ('cw-death',        'Death'),
            ('cw-slurs',        'Slurs'),
            ('cw-mature',       'Mature themes'),
        ],
    },
]


def seed() -> Dict[str, int]:
    """
    Insert any missing categories/tags. Returns counts added.
    Note: 'other' appears in two categories — slugs are globally unique,
    so we suffix the per-category 'other' tag slug with the category slug.
    """
    now = time.time()
    added_cats = 0
    added_tags = 0

    with get_db() as conn:
        conn.execute("BEGIN")
        try:
            for sort_idx, cat in enumerate(SEED):
                row = conn.execute(
                    "SELECT id FROM tag_categories WHERE slug = ?",
                    (cat['slug'],),
                ).fetchone()
                if row is None:
                    cur = conn.execute(
                        """INSERT INTO tag_categories
                           (slug, label, behavior, sort_order, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (cat['slug'], cat['label'], cat['behavior'], sort_idx, now),
                    )
                    cat_id = cur.lastrowid
                    added_cats += 1
                else:
                    cat_id = row['id']

                for tag_slug, tag_label in cat['tags']:
                    # Disambiguate 'other' across categories
                    final_slug = tag_slug if tag_slug != 'other' else f"other-{cat['slug']}"
                    exists = conn.execute(
                        "SELECT 1 FROM tags WHERE slug = ?",
                        (final_slug,),
                    ).fetchone()
                    if exists:
                        continue
                    conn.execute(
                        """INSERT INTO tags
                           (slug, label, category_id, status, suggested_by, created_at)
                           VALUES (?, ?, ?, 'active', NULL, ?)""",
                        (final_slug, tag_label, cat_id, now),
                    )
                    added_tags += 1

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return {'categories': added_cats, 'tags': added_tags}


if __name__ == '__main__':
    counts = seed()
    print(f"Seeded {counts['categories']} categories and {counts['tags']} tags")
