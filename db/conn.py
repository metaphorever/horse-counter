"""
db.conn - SQLite connection helper for poet.horse.

Single shared connection per process is fine for SQLite + Flask under gunicorn
with a small worker pool. We open with WAL + foreign keys and use Row factories
so callers can index by column name.

Usage:
    from db.conn import get_db, init_db

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM poems WHERE status='published'").fetchall()
        for row in rows:
            print(row['title'])
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from config import BASE_DIR

DB_PATH     = os.path.join(BASE_DIR, 'data', 'poet.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'db', 'schema.sql')

_local = threading.local()


def _connect() -> sqlite3.Connection:
    """Open a new connection with the project's standard pragmas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """
    Context manager yielding a per-thread connection.

    Implicit-transaction mode (isolation_level=None) means callers wrap their
    own writes in BEGIN/COMMIT when they want atomicity. Reads need no wrap.
    """
    conn = getattr(_local, 'conn', None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    try:
        yield conn
    except Exception:
        # Best-effort rollback if a transaction was open
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        raise


def init_db() -> None:
    """Apply schema.sql + column migrations + tag-taxonomy seeding. Idempotent."""
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        sql = f.read()
    with get_db() as conn:
        conn.executescript(sql)
    # Imported lazily to avoid a circular import (db.seed -> db.conn).
    from db.seed import run_all as _seed_run_all
    _seed_run_all()


def db_exists() -> bool:
    return os.path.exists(DB_PATH)
