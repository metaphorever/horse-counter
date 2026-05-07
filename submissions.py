"""
submissions.py - Public submission persistence

Submissions are stored in SUBMISSIONS_FILE (JSON on disk).
Each entry has a status: 'pending', 'approved', or 'rejected'.
"""

import os
import secrets
import time
from typing import Optional, Dict, Any, List

from config import BASE_DIR, read_json_file, write_json_file

SUBMISSIONS_FILE = os.path.join(BASE_DIR, 'submissions.json')


def _read() -> List[Dict]:
    return read_json_file(SUBMISSIONS_FILE, {'submissions': []}).get('submissions', [])


def _write(submissions: List[Dict]):
    write_json_file(SUBMISSIONS_FILE, {'submissions': submissions}, 'submissions')


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
