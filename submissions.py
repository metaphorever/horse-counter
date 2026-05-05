"""
submissions.py - Public submission persistence

Submissions are stored in SUBMISSIONS_FILE (JSON on disk).
Each entry has a status: 'pending', 'approved', or 'rejected'.
"""

import json
import os
import secrets
import time
from typing import Optional, Dict, Any, List

from config import BASE_DIR

SUBMISSIONS_FILE = os.path.join(BASE_DIR, 'submissions.json')


def _read() -> List[Dict]:
    if not os.path.exists(SUBMISSIONS_FILE):
        return []
    try:
        with open(SUBMISSIONS_FILE) as f:
            return json.load(f).get('submissions', [])
    except Exception:
        return []


def _write(submissions: List[Dict]):
    try:
        with open(SUBMISSIONS_FILE, 'w') as f:
            json.dump({'submissions': submissions}, f)
    except Exception as e:
        print(f"Submissions write error: {e}")


def save_submission(sub_type: str, data: Dict[str, Any]) -> str:
    subs   = _read()
    sub_id = secrets.token_urlsafe(16)
    subs.insert(0, {
        'id':           sub_id,
        'type':         sub_type,
        'status':       'pending',
        'submitted_at': time.time(),
        **data,
    })
    _write(subs)
    return sub_id


def load_pending() -> List[Dict]:
    return [s for s in _read() if s.get('status') == 'pending']


def load_submission(sub_id: str) -> Optional[Dict]:
    for s in _read():
        if s.get('id') == sub_id:
            return s
    return None


def update_status(sub_id: str, status: str):
    subs = _read()
    for s in subs:
        if s.get('id') == sub_id:
            s['status'] = status
            break
    _write(subs)
