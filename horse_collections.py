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
