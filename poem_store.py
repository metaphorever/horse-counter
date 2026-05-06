"""poem_store.py - Persist poems to disk for later gallery rendering."""

import json
import os
import time
import uuid
from typing import Dict, List, Optional

from config import BASE_DIR

POEMS_DIR  = os.path.join(BASE_DIR, 'data', 'poems')
INDEX_FILE = os.path.join(POEMS_DIR, 'index.json')


def _ensure_dir():
    os.makedirs(POEMS_DIR, exist_ok=True)


def load_index() -> List[Dict]:
    try:
        with open(INDEX_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_index(index: List[Dict]):
    _ensure_dir()
    with open(INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2)


def save_poem(
    lines: List[List[Dict]],
    title: str = '',
    author_name: str = '',
    author_tumblr: str = '',
    status: str = 'submitted',
    tumblr_post_id: Optional[str] = None,
) -> str:
    _ensure_dir()
    poem_id = uuid.uuid4().hex[:8]
    now = time.time()

    poem = {
        'id':             poem_id,
        'title':          title,
        'author_name':    author_name,
        'author_tumblr':  author_tumblr,
        'status':         status,
        'submitted_at':   now,
        'tumblr_post_id': tumblr_post_id,
        'lines':          lines,
    }

    with open(os.path.join(POEMS_DIR, f'{poem_id}.json'), 'w') as f:
        json.dump(poem, f, indent=2)

    index = load_index()
    index.append({
        'id':            poem_id,
        'title':         title,
        'author_name':   author_name,
        'author_tumblr': author_tumblr,
        'status':        status,
        'submitted_at':  now,
    })
    _save_index(index)

    return poem_id


def load_poem(poem_id: str) -> Optional[Dict]:
    path = os.path.join(POEMS_DIR, f'{poem_id}.json')
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None
