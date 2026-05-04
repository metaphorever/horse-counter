"""
poetry.py - Poetry editor backend
"""

import json
import os
import re
import time
from typing import List, Dict, Optional, Tuple, Callable

from config import BASE_DIR, OPTIONAL_TAGS

PASTURE_FILE    = os.path.join(BASE_DIR, 'pasture.json')
SEARCH_LIMIT    = 20
SEARCH_HARD_CAP = 500

POEM_PREFIX_TEMPLATE = (
    "<p><b>This poem contains {count} horse{plural} "
    "({density}% of the poem)</b></p>"
)
POEM_SUFFIX = (
    "<p><small>This poem was written by a human, processed automatically "
    "and queued to post. Click any name for more information about that horse. "
    "You can send a link or text to be counted to my ask box.</small></p>"
)
POEM_TAGS = [
    "{count} horses",
    "{density}% horse",
    "horse poetry",
    "poetry",
    "gimmick account",
    "counting-horses",
    "horseblr",
]


def build_poem_tags(count: int, density: float) -> List[str]:
    return [
        t.replace('{count}', str(count)).replace('{density}', str(density))
        for t in POEM_TAGS
    ]


def format_poem_prefix(count: int, density: float) -> str:
    plural = 's' if count != 1 else ''
    return POEM_PREFIX_TEMPLATE.format(count=count, plural=plural, density=density)


# ── Search ────────────────────────────────────────────────────────────────────

def _compile_search(query: str):
    q = query.strip().lower()
    if not q:
        return None, "Enter a search term"

    core = q.replace('*', '').replace(' ', '')
    if len(core) < 3:
        return None, "Enter at least 3 characters (not counting * or spaces)"

    parts = q.split('*')

    if len(parts) == 1:
        pattern = '^' + re.escape(q) + '$'
    else:
        regex_parts = []
        for i, part in enumerate(parts):
            if part == '':
                regex_parts.append('.*')
                continue
            has_leading  = part.startswith(' ')
            has_trailing = part.endswith(' ')
            clean_words  = [w for w in part.split(' ') if w]
            word_pat     = r'\s+'.join(re.escape(w) for w in clean_words)
            if has_leading:
                word_pat = r'(?<=\s)' + word_pat
            if has_trailing:
                word_pat = word_pat + r'(?=\s)'
            regex_parts.append(word_pat)
            if i < len(parts) - 1:
                regex_parts.append('.*')

        pattern = ''.join(regex_parts)

        if not q.startswith('*'):
            pattern = '^' + pattern
        if not q.endswith('*'):
            pattern = pattern + '$'

        if q.endswith(' *'):
            pattern = pattern.rstrip('$')
            pattern = re.sub(r'\.\*$', r'\\s+\\S.*', pattern)
        if q.startswith('* '):
            pattern = pattern.lstrip('^')
            pattern = r'^.+\s' + pattern.lstrip('.*')

    try:
        compiled = re.compile(pattern)
        return lambda name, c=compiled: bool(c.search(name)), None
    except re.error as e:
        return None, f"Invalid pattern: {e}"


def _describe_mode(query: str) -> str:
    q = query.strip()
    if '*' not in q:
        return f'Exact: horse named exactly "{q}"'
    if q.startswith('*') and q.endswith('*') and q.count('*') == 2:
        return f'Contains "{q[1:-1].strip()}" anywhere'
    if q.endswith('*') and not q.startswith('*'):
        return f'Starts with "{q.rstrip("* ")}"'
    if q.startswith('*') and not q.endswith('*'):
        return f'Ends with "{q.lstrip("* ")}"'
    if q.endswith(' *') and not q.startswith('*'):
        return f'"{q.rstrip(" *")}" is the first word'
    if q.startswith('* ') and not q.endswith('*'):
        return f'"{q.lstrip("* ")}" is the last word'
    return f'Pattern: {q}'


def search_dictionary(query: str, dictionary, limit: int = SEARCH_LIMIT, return_all: bool = False) -> Dict:
    matcher, err = _compile_search(query.strip())
    if err:
        return {'results': [], 'total': 0, 'limited': False, 'query': query, 'error': err, 'mode': ''}

    cap   = SEARCH_HARD_CAP if return_all else limit
    found = []

    for name, registrations in dictionary.horses.items():
        if matcher(name):
            reg = registrations[0]
            found.append({
                'name':    name,
                'display': reg.get('display_name', ' '.join(w.capitalize() for w in name.split())),
                'url':     reg.get('url', ''),
                'count':   len(registrations),
            })
            if len(found) >= cap:
                break

    total   = len(found)
    limited = not return_all and total >= limit

    if limited:
        true_total = sum(1 for name in dictionary.horses if matcher(name))
        total = true_total

    q_core = query.strip().lower().replace('*', '').strip()
    found.sort(key=lambda x: (
        0 if x['name'] == q_core else 1 if x['name'].startswith(q_core) else 2,
        x['name'],
    ))

    return {
        'results': found[:cap],
        'total':   total,
        'limited': limited,
        'query':   query,
        'error':   None,
        'mode':    _describe_mode(query.strip()),
    }


# ── Pasture ───────────────────────────────────────────────────────────────────

def load_pasture() -> List[Dict]:
    if not os.path.exists(PASTURE_FILE):
        return []
    try:
        with open(PASTURE_FILE) as f:
            return json.load(f).get('horses', [])
    except Exception:
        return []


def save_pasture(horses: List[Dict]):
    try:
        with open(PASTURE_FILE, 'w') as f:
            json.dump({'horses': horses, 'updated': time.time()}, f)
    except Exception as e:
        print(f"Pasture save error: {e}")


def add_to_pasture(name: str, display: str, url: str) -> List[Dict]:
    horses = load_pasture()
    if not any(h['name'] == name for h in horses):
        horses.append({'name': name, 'display': display, 'url': url})
        save_pasture(horses)
    return horses


def remove_from_pasture(name: str) -> List[Dict]:
    horses = [h for h in load_pasture() if h['name'] != name]
    save_pasture(horses)
    return horses


def clear_pasture():
    save_pasture([])


# ── Poem post building ────────────────────────────────────────────────────────

def build_poem_html(lines: List[List[Dict]]) -> str:
    html_lines = []
    for line in lines:
        if not line:
            continue
        linked = ' '.join(f'<a href="{h["url"]}">{h["display"]}</a>' for h in line)
        html_lines.append(f'<p>{linked}</p>')
    return '\n'.join(html_lines)


def compute_poem_stats(lines: List[List[Dict]]) -> Dict:
    total_names = sum(len(line) for line in lines)
    total_words = sum(len(h['name'].split()) for line in lines for h in line)
    return {'total_names': total_names, 'total_words': total_words, 'horse_density': 100.0}