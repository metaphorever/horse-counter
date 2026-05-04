"""
queue_handler.py - Draft persistence and posting to Tumblr

Drafts are stored in DRAFTS_FILE (JSON on disk) so they survive
PythonAnywhere worker restarts. Each draft has a TTL; expired drafts
are pruned on each write.

Posting strategy:
- Normal reblog:  POST /blog/{blog}/post/reblog  (legacy v1 endpoint, still works)
- Fallback post:  POST /blog/{blog}/post          (text post, used when no reblog key)
- Text-only post: POST /blog/{blog}/post          (for ask replies / standalone)
"""

import json
import os
import secrets
import time
from typing import Optional, Dict, Any

from config import DRAFTS_FILE, DRAFT_TTL_SECONDS, TUMBLR_BLOG_NAME


# ── Draft storage ─────────────────────────────────────────────────────────────

def _read_drafts() -> Dict[str, Any]:
    if not os.path.exists(DRAFTS_FILE):
        return {}
    try:
        with open(DRAFTS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_drafts(drafts: Dict[str, Any]):
    # Prune expired drafts before writing
    now = time.time()
    drafts = {k: v for k, v in drafts.items() if v.get('expires', 0) > now}
    try:
        with open(DRAFTS_FILE, 'w') as f:
            json.dump(drafts, f)
    except Exception as e:
        print(f"Draft write error: {e}")


def save_draft(payload: Dict[str, Any]) -> str:
    """Store a draft and return its ID."""
    drafts = _read_drafts()
    draft_id = secrets.token_urlsafe(16)
    drafts[draft_id] = {
        **payload,
        'expires': time.time() + DRAFT_TTL_SECONDS,
    }
    _write_drafts(drafts)
    return draft_id


def load_draft(draft_id: str) -> Optional[Dict[str, Any]]:
    """Return draft if it exists and hasn't expired, else None."""
    drafts = _read_drafts()
    draft = drafts.get(draft_id)
    if not draft:
        return None
    if draft.get('expires', 0) < time.time():
        return None
    return draft


def delete_draft(draft_id: str):
    drafts = _read_drafts()
    drafts.pop(draft_id, None)
    _write_drafts(drafts)


# ── Tag assembly ──────────────────────────────────────────────────────────────

def assemble_tags(
    default_tags:  list,
    optional_tags: list,
    custom_tags:   str,
) -> str:
    """Combine all tag sources into a comma-separated string."""
    tags = list(default_tags) + list(optional_tags)
    if custom_tags:
        extras = [t.strip() for t in custom_tags.split(',') if t.strip()]
        tags.extend(extras)
    return ','.join(tags)


# ── HTML assembly ─────────────────────────────────────────────────────────────

def build_post_body(
    prefix:      str,
    linked_html: str,
    middle:      str,
    suffix:      str,
) -> str:
    """Assemble the final HTML body for a post."""
    parts = [prefix, f'<blockquote>{linked_html}</blockquote>']
    if middle.strip():
        parts.append(middle)
    parts.append(suffix)
    return ''.join(parts)


# ── Posting ───────────────────────────────────────────────────────────────────

def _post_state(action: str) -> str:
    return {'post': 'published', 'queue': 'queue', 'draft': 'draft'}.get(action, 'queue')


def submit_post(
    draft:      Dict[str, Any],
    action:     str,
    body:       str,
    tags:       str,
    make_request,           # TumblrManager.make_request
) -> tuple[bool, str]:
    """
    Submit the post to Tumblr.
    Returns (success: bool, error_message: str).
    """
    state = _post_state(action)

    # ── Text-only post (ask reply, standalone) ────────────────────────────────
    if draft.get('is_text_post'):
        return _create_text_post(
            make_request, body, tags, state,
            title=''
        )

    # ── Fallback: no reblog key available ─────────────────────────────────────
    if draft.get('is_fallback'):
        return _create_text_post(
            make_request, body, tags, state,
            title=''
        )

    # ── Reblog (normal URL post and reply mode) ───────────────────────────────
    post_data = draft.get('post_data', {})
    post_id   = post_data.get('post_id', '')
    reblog_key = post_data.get('reblog_key', '')

    if not post_id or not reblog_key:
        # Missing reblog key — fall back to text post and note the issue
        print(f"Warning: missing reblog key for post {post_id}, creating text post")
        return _create_text_post(
            make_request, body, tags, state,
            title=''
        )

    return _create_reblog(make_request, post_id, reblog_key, body, tags, state)


def _create_reblog(
    make_request,
    post_id:    str,
    reblog_key: str,
    body:       str,
    tags:       str,
    state:      str,
) -> tuple[bool, str]:
    """
    Reblog using the v1 /post/reblog endpoint.
    This endpoint still works as of 2024 and is the correct way to reblog
    with a comment via the API (NPF reblog via /posts requires extra steps).
    """
    data = {
        'id':         post_id,
        'reblog_key': reblog_key,
        'comment':    body,
        'state':      state,
        'tags':       tags,
    }
    result = make_request(f'blog/{TUMBLR_BLOG_NAME}/post/reblog', 'POST', data)

    if result:
        meta_status = result.get('meta', {}).get('status')
        if meta_status in (200, 201):
            return True, ''
        # Some versions return status at top level
        if result.get('status') in (200, 201):
            return True, ''
        # Check for response id (v2 style success)
        if result.get('response', {}).get('id'):
            return True, ''

    return False, f"Reblog API call failed. Response: {result}"


def _create_text_post(
    make_request,
    body:  str,
    tags:  str,
    state: str,
    title: str = '',
) -> tuple[bool, str]:
    data = {
        'type':  'text',
        'state': state,
        'title': title,
        'body':  body,
        'tags':  tags,
    }
    result = make_request(f'blog/{TUMBLR_BLOG_NAME}/post', 'POST', data)

    if result:
        meta_status = result.get('meta', {}).get('status')
        if meta_status in (200, 201):
            return True, ''
        if result.get('status') in (200, 201):
            return True, ''
        if result.get('response', {}).get('id'):
            return True, ''

    return False, f"Text post API call failed. Response: {result}"