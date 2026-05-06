"""
post_builder.py - Fetch and parse Tumblr posts into a normalised chain structure.

A "chain" is a list of dicts:
    [
        {'username': 'blog-name', 'text': 'raw text with markers'},
        ...
    ]

The chain is in chronological order: index 0 is the original post,
last item is the most recent reblogger (the current poster).

NPF v2 trail fix: trail[] contains everyone EXCEPT the current poster.
The current poster's content lives in the top-level 'content' array.
We append it explicitly after processing trail.
"""

import json
import re
import time
import urllib.parse
from typing import Optional, List, Dict

import requests
from bs4 import BeautifulSoup

from config import TUMBLR_CONSUMER_KEY


# ── URL parsing ───────────────────────────────────────────────────────────────

def parse_tumblr_url(url: str):
    """Return (blog_name, post_id) or (None, None)."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ''

        blog_name = None
        if 'tumblr.com' in host:
            if host.startswith('www.'):
                parts = parsed.path.strip('/').split('/')
                blog_name = parts[0] if parts else None
            else:
                blog_name = host.split('.')[0]

        post_id = None
        path_parts = parsed.path.strip('/').split('/')
        for i, part in enumerate(path_parts):
            if part == 'post' and i + 1 < len(path_parts):
                post_id = path_parts[i + 1]
                break
            elif part.isdigit() and len(part) >= 10:
                post_id = part
                break

        if post_id:
            post_id = ''.join(filter(str.isdigit, post_id))

        return blog_name, post_id
    except Exception:
        return None, None


# ── Content block extraction ──────────────────────────────────────────────────

def _blocks_to_text(blocks: List[Dict]) -> str:
    """
    Convert an NPF content block list to plain text with image markers.
    Preserves paragraph spacing between blocks.
    """
    parts = []
    for block in blocks:
        btype = block.get('type', '')
        if btype == 'text':
            parts.append(block.get('text', ''))
        elif btype == 'image':
            alt = block.get('alt_text', '').strip()
            media = block.get('media', [])
            is_gif = any(
                m.get('type', '') == 'image/gif' or
                str(m.get('url', '')).lower().endswith('.gif')
                for m in media
            )
            prefix = 'GIF' if is_gif else 'IMAGE'
            if alt:
                parts.append(f'\n\n[[[{prefix}_DESC:{alt}]]]\n\n')
            else:
                parts.append(f'\n\n[[[{prefix}]]]\n\n')
        elif btype == 'video':
            parts.append('\n\n[[[VIDEO]]]\n\n')
        # Other block types (audio, link) are intentionally ignored
    return '\n\n'.join(p for p in parts if p.strip())


def _clean(text: str) -> str:
    """Strip HTML tags from text, preserving newlines."""
    if not text:
        return ''
    # Replace block-level tags with newlines before stripping
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</div>', '\n', text, flags=re.IGNORECASE)
    return BeautifulSoup(text, 'html.parser').get_text()


# ── Chain parsing ─────────────────────────────────────────────────────────────

def _parse_npf_post(post: Dict, blog_name: str, post_id: str, url: str) -> Optional[Dict]:
    """
    Parse a full NPF v2 post object into our chain structure.

    NPF trail fix implemented here:
    - trail[] has everyone except the current poster
    - post['content'] + post['blog_name'] is the current poster
    """
    try:
        chain = []
        trail = post.get('trail', [])

        # ── Process trail items (all previous reblogs) ──
        for item in trail:
            blog = item.get('blog', {})
            username = blog.get('name', 'unknown')
            blocks = item.get('content', [])
            if blocks:
                raw = _blocks_to_text(blocks)
                text = _clean(raw)
                if text.strip():
                    chain.append({'username': username, 'text': text.strip()})

        # ── Append current poster (the NPF trail fix) ──
        current_blocks = post.get('content', [])
        if current_blocks:
            raw = _blocks_to_text(current_blocks)
            text = _clean(raw)
            if text.strip():
                current_blog = post.get('blog_name', blog_name)
                chain.append({'username': current_blog, 'text': text.strip()})

        # ── Legacy post types fallback ──
        if not chain:
            ptype = post.get('type', '')
            text = ''
            if ptype == 'text':
                text = _clean(post.get('body', ''))
            elif ptype == 'quote':
                text = _clean(post.get('text', ''))
            elif ptype == 'chat':
                dialogue = post.get('dialogue', [])
                text = '\n'.join(
                    f"{d.get('name', '')}: {d.get('phrase', '')}"
                    for d in dialogue
                )
            if text.strip():
                chain.append({'username': blog_name, 'text': text.strip()})

        if not chain:
            return None

        return {
            'blog_name':  blog_name,
            'post_id':    post_id,
            'post_url':   post.get('post_url', url),
            'reblog_key': post.get('reblog_key', ''),
            'chain':      chain,
            'is_multi':   len(chain) > 1,
            'is_fallback': False,
        }

    except Exception as e:
        print(f"_parse_npf_post error: {e}")
        return None


# ── API extraction methods ────────────────────────────────────────────────────

def _fetch_api_authenticated(url: str, make_request) -> Optional[Dict]:
    """Authenticated API v2 request using the TumblrManager callable."""
    blog_name, post_id = parse_tumblr_url(url)
    if not blog_name or not post_id:
        return None

    for endpoint in [
        f'blog/{blog_name}.tumblr.com/posts',
        f'blog/{blog_name}/posts',
    ]:
        data = make_request(endpoint, 'GET', {'id': post_id, 'npf': 'true'})
        if data:
            posts = data.get('response', {}).get('posts', [])
            if posts:
                return _parse_npf_post(posts[0], blog_name, post_id, url)
    return None


def _fetch_api_public(url: str) -> Optional[Dict]:
    """Public API with consumer key only (no auth required for public posts)."""
    if not TUMBLR_CONSUMER_KEY:
        return None

    blog_name, post_id = parse_tumblr_url(url)
    if not blog_name or not post_id:
        return None

    for endpoint in [
        f'https://api.tumblr.com/v2/blog/{blog_name}.tumblr.com/posts',
        f'https://api.tumblr.com/v2/blog/{blog_name}/posts',
    ]:
        try:
            r = requests.get(
                endpoint,
                params={'api_key': TUMBLR_CONSUMER_KEY, 'id': post_id, 'npf': 'true'},
                timeout=10,
            )
            if r.status_code == 200:
                posts = r.json().get('response', {}).get('posts', [])
                if posts:
                    return _parse_npf_post(posts[0], blog_name, post_id, url)
        except Exception:
            continue
    return None


def _fetch_api_v1_legacy(url: str) -> Optional[Dict]:
    """Legacy API v1 JSON endpoint."""
    blog_name, post_id = parse_tumblr_url(url)
    if not blog_name or not post_id:
        return None

    legacy_urls = [
        f'https://{blog_name}.tumblr.com/api/read/json?id={post_id}',
        f'https://{blog_name}.tumblr.com/api/read/json?id={post_id}&filter=none',
    ]

    for legacy_url in legacy_urls:
        try:
            r = requests.get(legacy_url, timeout=10)
            if r.status_code != 200:
                continue

            json_text = r.text
            if json_text.startswith('var tumblr_api_read = '):
                json_text = json_text[len('var tumblr_api_read = '):]
                if json_text.endswith(';'):
                    json_text = json_text[:-1]

            data = json.loads(json_text)
            posts = data.get('posts', [])
            if not posts:
                continue

            post = posts[0]
            text = _clean(
                post.get('regular-body', '')
                or post.get('quote-text', '')
                or ''
            )
            if text.strip():
                return {
                    'blog_name':   blog_name,
                    'post_id':     post_id,
                    'post_url':    url,
                    'reblog_key':  '',
                    'chain':       [{'username': blog_name, 'text': text.strip()}],
                    'is_multi':    False,
                    'is_fallback': True,
                }
        except Exception:
            continue
    return None


def _fetch_scrape_fallback(url: str) -> Optional[Dict]:
    """
    Last-resort web scraping.
    Note: Tumblr's frontend is JS-rendered so this often returns minimal content.
    Marked as is_fallback=True so the queue handler creates a text post instead
    of attempting a reblog.
    """
    try:
        headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        }
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, 'html.parser')

        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ''
        blog_name = 'unknown'
        if 'tumblr.com' in host:
            if host.startswith('www.'):
                parts = parsed.path.strip('/').split('/')
                blog_name = parts[0] if parts else 'unknown'
            else:
                blog_name = host.split('.')[0]

        post_text = ''

        # Try JSON-LD / embedded JSON first
        for script in soup.find_all('script', type='application/json'):
            try:
                data = json.loads(script.string or '')
                texts = _extract_text_from_json(data)
                if texts:
                    post_text = ' '.join(texts)
                    break
            except Exception:
                continue

        # Try semantic HTML selectors
        if not post_text:
            for selector in [
                'article[data-id]', '[data-post-id]',
                '.post-content', '.post', 'article',
            ]:
                elements = soup.select(selector)
                if elements:
                    texts = []
                    for el in elements:
                        for unwanted in el(['script', 'style', 'nav', 'header', 'footer']):
                            unwanted.decompose()
                        t = el.get_text(separator='\n', strip=True)
                        if len(t) > 20:
                            texts.append(t)
                    if texts:
                        post_text = '\n\n'.join(texts)
                        break

        # Paragraph fallback
        if len(post_text) < 20:
            paras = [p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 10]
            post_text = '\n\n'.join(paras)

        if len(post_text) < 10:
            return None

        return {
            'blog_name':   blog_name,
            'post_id':     'scraped',
            'post_url':    url,
            'reblog_key':  '',
            'chain':       [{'username': blog_name, 'text': post_text.strip()}],
            'is_multi':    False,
            'is_fallback': True,
        }

    except Exception as e:
        print(f"Scrape fallback error: {e}")
        return None


def _extract_text_from_json(data) -> List[str]:
    texts = []
    if isinstance(data, dict):
        for key, val in data.items():
            if key == 'text' and isinstance(val, str) and len(val) > 20:
                texts.append(val)
            elif isinstance(val, (dict, list)):
                texts.extend(_extract_text_from_json(val))
    elif isinstance(data, list):
        for item in data:
            texts.extend(_extract_text_from_json(item))
    return texts


# ── Public interface ──────────────────────────────────────────────────────────

def extract_post(url: str, make_api_request=None) -> Optional[Dict]:
    """
    Fetch a Tumblr post with cascading fallbacks.
    make_api_request: callable from TumblrManager, or None if not authenticated.
    Returns a post dict or None.
    """
    # 1. Authenticated API (best quality, has reblog keys)
    if make_api_request:
        result = _fetch_api_authenticated(url, make_api_request)
        if result:
            return result

    # 2. Public API (works for public posts without auth)
    result = _fetch_api_public(url)
    if result:
        return result

    # 3. Legacy v1 API
    result = _fetch_api_v1_legacy(url)
    if result:
        return result

    # 4. Scraping (last resort, often incomplete on JS-rendered pages)
    return _fetch_scrape_fallback(url)
