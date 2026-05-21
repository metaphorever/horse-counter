"""
horse_collections.py - Per-user Pasture and Saved Horses collections.

Pasture:   working storage for horses ("save for later").
           Uses the pasture_horses table (name/display/url columns).
Saved:     blue-ribbon sentiment signal. Private; feeds admin stats only.
Both are private — never surfaced as public counts.
"""

import time
from typing import Dict, List

from db.conn import get_db


# ── Pasture ───────────────────────────────────────────────────────────────────

def toggle_pasture(user_id: int, name: str, display: str, url: str = '') -> Dict:
    """Add or remove a horse from the user's pasture. Returns {in_pasture: bool}."""
    name    = (name    or '').strip()
    display = (display or name).strip()
    url     = (url     or '').strip()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM pasture_horses WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM pasture_horses WHERE user_id = ? AND name = ?",
                (user_id, name),
            )
            return {'in_pasture': False}
        conn.execute(
            "INSERT OR IGNORE INTO pasture_horses (user_id, name, display, url, added_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, name, display, url, time.time()),
        )
        return {'in_pasture': True}


# ── Saved horses ──────────────────────────────────────────────────────────────

def toggle_saved_horse(user_id: int, name: str, display: str, url: str = '') -> Dict:
    """Toggle the blue-ribbon save on a horse. Returns {saved: bool}."""
    name    = (name    or '').strip()
    display = (display or name).strip()
    url     = (url     or '').strip()
    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM saved_horses WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM saved_horses WHERE user_id = ? AND name = ?",
                (user_id, name),
            )
            return {'saved': False}
        conn.execute(
            "INSERT OR IGNORE INTO saved_horses (user_id, name, display, url, saved_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, name, display, url, time.time()),
        )
        return {'saved': True}


# ── Pasture — remove (Phase 1.19) ─────────────────────────────────────────────

def remove_from_pasture(user_id: int, name: str) -> bool:
    """Remove a single horse from the user's pasture. Returns True if it was there."""
    name = (name or '').strip()
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM pasture_horses WHERE user_id = ? AND name = ?",
            (user_id, name),
        )
        return cur.rowcount > 0


def list_saved_horses(user_id: int) -> list:
    """Return all ribbon-saved horses for a user, newest first."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name, display, url, saved_at FROM saved_horses WHERE user_id = ? ORDER BY saved_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Saved poems (Phase 1.19) ──────────────────────────────────────────────────

def toggle_saved_poem(user_id: int, poem_id: int) -> dict:
    """Toggle the blue-ribbon save on a poem. Returns {saved: bool}."""
    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM saved_poems WHERE user_id = ? AND poem_id = ?",
            (user_id, poem_id),
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM saved_poems WHERE user_id = ? AND poem_id = ?",
                (user_id, poem_id),
            )
            return {'saved': False}
        conn.execute(
            "INSERT OR IGNORE INTO saved_poems (user_id, poem_id, saved_at) VALUES (?, ?, ?)",
            (user_id, poem_id, time.time()),
        )
        return {'saved': True}


def is_poem_saved(user_id: int, poem_id: int) -> bool:
    with get_db() as conn:
        return conn.execute(
            "SELECT 1 FROM saved_poems WHERE user_id = ? AND poem_id = ?",
            (user_id, poem_id),
        ).fetchone() is not None


def list_saved_poems(user_id: int) -> list:
    """Return saved poems with display fields, newest-saved first."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.short_code, p.title, p.horse_count, p.published_at,
                      p.author_display_name, p.author_user_id,
                      u.display_name AS author_name, u.slug AS author_slug,
                      sp.saved_at
                 FROM saved_poems sp
                 JOIN poems p ON p.id = sp.poem_id
                 LEFT JOIN users u ON u.id = p.author_user_id
                WHERE sp.user_id = ?
                ORDER BY sp.saved_at DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Bulk state check ──────────────────────────────────────────────────────────

def get_horse_states(user_id: int, horse_names: List[str]) -> Dict[str, Dict]:
    """
    Return {name: {in_pasture, saved}} for each name in horse_names.
    Two queries regardless of list length.
    """
    if not horse_names:
        return {}
    states = {n: {'in_pasture': False, 'saved': False} for n in horse_names}
    placeholders = ','.join('?' * len(horse_names))
    with get_db() as conn:
        for row in conn.execute(
            f"SELECT name FROM pasture_horses WHERE user_id = ? AND name IN ({placeholders})",
            (user_id, *horse_names),
        ).fetchall():
            states[row['name']]['in_pasture'] = True
        for row in conn.execute(
            f"SELECT name FROM saved_horses WHERE user_id = ? AND name IN ({placeholders})",
            (user_id, *horse_names),
        ).fetchall():
            states[row['name']]['saved'] = True
    return states
