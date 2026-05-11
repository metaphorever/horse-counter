"""
tools/init_db.py - Create / migrate the SQLite database.

Run from repo root:
    python -m tools.init_db

Idempotent: safe to run repeatedly. Applies schema and (optionally) seeds tags.
"""

import argparse
import sys

from db.conn import db_exists, init_db, DB_PATH


def main():
    parser = argparse.ArgumentParser(description='Initialise the poet.horse SQLite database')
    parser.add_argument('--seed-tags', action='store_true',
                        help='Also seed the default tag categories and tags')
    args = parser.parse_args()

    fresh = not db_exists()
    init_db()
    print(f"{'Created' if fresh else 'Verified'} {DB_PATH}")

    if args.seed_tags:
        from tools.seed_tags import seed
        added = seed()
        print(f"Seeded tags: {added['categories']} categories, {added['tags']} tags")


if __name__ == '__main__':
    sys.exit(main() or 0)
