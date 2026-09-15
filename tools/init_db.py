"""
tools/init_db.py - Create / migrate the SQLite database.

Run from repo root:
    python -m tools.init_db

Idempotent: safe to run repeatedly. Applies schema, column migrations, and the
tag taxonomy (db/seed.py) — the same init_db() the app runs at import.
"""

import argparse
import sys

from db.conn import db_exists, init_db, DB_PATH


def main():
    parser = argparse.ArgumentParser(description='Initialise the poet.horse SQLite database')
    parser.parse_args()

    fresh = not db_exists()
    init_db()
    print(f"{'Created' if fresh else 'Verified'} {DB_PATH}")


if __name__ == '__main__':
    sys.exit(main() or 0)
