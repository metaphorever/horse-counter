"""
poetry.py - Poetry editor backend
"""

import json
import os
import random as _random
import re
import time
import urllib.parse
import requests as _requests
from typing import List, Dict, Optional, Tuple, Callable

from config import BASE_DIR, OPTIONAL_TAGS

STABLE_FILE        = os.path.join(BASE_DIR, 'stable.json')
_PASTURE_LEGACY    = os.path.join(BASE_DIR, 'pasture.json')  # migrated on first load
SEARCH_HARD_CAP    = 500
RHYME_TERMS_MAX      = 50   # max terms to fetch from Datamuse
RHYME_DEFAULT_ON     = 6    # how many chips are checked by default
RHYME_CAP_PER_TERM   = 200  # max horse matches per rhyme word (before dedup)

THESAURUS_TERMS_MAX    = 50   # max related words from Datamuse
THESAURUS_DEFAULT_ON   = 6    # how many chips are checked by default
THESAURUS_CAP_PER_TERM = 200  # max horse matches per synonym (before dedup)

_datamuse_cache: Dict = {}


def get_rhymes(word: str) -> List[Dict]:
    """Fetch perfect rhymes from Datamuse. Returns [{word, score}] sorted by score desc."""
    key = ('rhy', word.lower().strip())
    if key in _datamuse_cache:
        return _datamuse_cache[key]
    url = f'https://api.datamuse.com/words?rel_rhy={urllib.parse.quote(word)}&max={RHYME_TERMS_MAX}'
    try:
        r = _requests.get(url, timeout=4, headers={'User-Agent': 'horse-counter/1.0'})
        r.raise_for_status()
        results = [{'word': item['word'], 'score': item.get('score', 0)} for item in r.json()]
    except Exception:
        results = []
    _datamuse_cache[key] = results
    return results


def search_by_rhyme_terms(terms: List[str], dictionary) -> List[Dict]:
    """For each term, find horses whose name ends with that term. Deduplicates across terms."""
    results = []
    seen: set = set()
    for term in terms:
        if len(term) < 3:
            continue
        matcher, err = _compile_search(f'*{term}')
        if err or matcher is None:
            continue
        count = 0
        for name, registrations in dictionary.horses.items():
            if name in seen:
                continue
            if matcher(name):
                reg = registrations[0]
                results.append({
                    'name':         name,
                    'display':      reg.get('display_name', ' '.join(w.capitalize() for w in name.split())),
                    'url':          reg.get('url', ''),
                    'count':        len(registrations),
                    'matched_term': term,
                })
                seen.add(name)
                count += 1
                if count >= RHYME_CAP_PER_TERM:
                    break
    return results


def get_synonyms(word: str) -> List[Dict]:
    """Fetch semantically related words from Datamuse 'means like'. Returns [{word, score}]."""
    key = ('ml', word.lower().strip())
    if key in _datamuse_cache:
        return _datamuse_cache[key]
    url = f'https://api.datamuse.com/words?ml={urllib.parse.quote(word)}&max={THESAURUS_TERMS_MAX}'
    try:
        r = _requests.get(url, timeout=4, headers={'User-Agent': 'horse-counter/1.0'})
        r.raise_for_status()
        results = [{'word': item['word'], 'score': item.get('score', 0)} for item in r.json()]
    except Exception:
        results = []
    _datamuse_cache[key] = results
    return results


def search_by_synonym_terms(terms: List[str], dictionary) -> List[Dict]:
    """For each term, find horses whose name contains that term anywhere. Deduplicates across terms."""
    results = []
    seen: set = set()
    for term in terms:
        if len(term) < 3:
            continue
        matcher, err = _compile_search(f'*{term}*')
        if err or matcher is None:
            continue
        count = 0
        for name, registrations in dictionary.horses.items():
            if name in seen:
                continue
            if matcher(name):
                reg = registrations[0]
                results.append({
                    'name':         name,
                    'display':      reg.get('display_name', ' '.join(w.capitalize() for w in name.split())),
                    'url':          reg.get('url', ''),
                    'count':        len(registrations),
                    'matched_term': term,
                })
                seen.add(name)
                count += 1
                if count >= THESAURUS_CAP_PER_TERM:
                    break
    return results


POEM_SUFFIX = (
    "<p><small>This poem was written by a human, processed automatically, "
    "and queued to post. Click the links for more information about each horse. "
    "You can write and submit your own horse poetry at "
    "<a href=\"https://horsecounterbot.pythonanywhere.com/poetry\">"
    "horsecounterbot.pythonanywhere.com/poetry</a>.</small></p>"
)
def build_poem_tags(count: int, name: str = '', tumblr: str = '', is_admin: bool = False) -> List[str]:
    plural = 's' if count != 1 else ''
    tags = ['horse poetry']
    if name:
        tags.append(f'by {name}')
    if tumblr:
        tags.append(tumblr)
    tags += ['how many horses?', f'{count} horse{plural}', '100% horse']
    if not is_admin or (name or tumblr):
        tags.append('user submission')
    tags += ['poetry', 'text post', 'counting-horses', 'gimmick account', 'horseblr']
    return tags


def order_tags(tags_str: str, first: str, *prepend: str, force_first: bool = True) -> str:
    """
    Re-order a comma-separated tag string so `first` leads, followed by any
    `prepend` items, then the remaining tags.

    force_first=True  — always include `first` even if not in tags_str (e.g. 'request')
    force_first=False — only include `first` when it already appears (e.g. 'horse poetry')
    """
    parts = [t.strip() for t in tags_str.split(',') if t.strip()]
    extra = [t for t in prepend if t]
    excluded = {first} | set(extra)
    rest = [t for t in parts if t not in excluded]
    include_first = first and (force_first or (first in parts))
    front = ([first] if include_first else []) + extra
    return ','.join(front + rest)


def format_poem_prefix(count: int, title: str = '', name: str = '', tumblr: str = '') -> str:
    plural = 's' if count != 1 else ''
    display = name or (f'@{tumblr}' if tumblr else '')
    if display and tumblr:
        author_html = f'<a href="https://www.tumblr.com/{tumblr}">{display}</a>'
    elif display:
        author_html = display
    else:
        author_html = ''
    if title and author_html:
        subject = f'<em>{title}</em> by {author_html}'
    elif title:
        subject = f'<em>{title}</em>'
    elif author_html:
        subject = f'This poem by {author_html}'
    else:
        subject = 'This poem'
    return f'<p><b>{subject} contains {count} horse{plural}</b></p>'


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


def search_dictionary(query: str, dictionary) -> Dict:
    matcher, err = _compile_search(query.strip())
    if err:
        return {'results': [], 'total': 0, 'capped': False, 'query': query, 'error': err, 'mode': ''}

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
            if len(found) >= SEARCH_HARD_CAP:
                break

    capped = len(found) >= SEARCH_HARD_CAP

    q_core = query.strip().lower().replace('*', '').strip()
    found.sort(key=lambda x: (
        0 if x['name'] == q_core else 1 if x['name'].startswith(q_core) else 2,
        x['name'],
    ))

    return {
        'results': found,
        'total':   len(found),
        'capped':  capped,
        'query':   query,
        'error':   None,
        'mode':    _describe_mode(query.strip()),
    }


def short_horses(dictionary, max_len: int = 3) -> List[Dict]:
    results = []
    for name, registrations in dictionary.horses.items():
        if len(name) <= max_len:
            reg = registrations[0]
            results.append({
                'name':         name,
                'display':      reg.get('display_name', ' '.join(w.capitalize() for w in name.split())),
                'url':          reg.get('url', ''),
                'count':        len(registrations),
                'matched_term': f'{len(name)} letter{"s" if len(name) != 1 else ""}',
            })
    results.sort(key=lambda h: (len(h['name']), h['name']))
    return results


def random_horses(dictionary, n: int = 5) -> List[Dict]:
    items = list(dictionary.horses.items())
    sample = _random.sample(items, min(n, len(items)))
    results = []
    for name, registrations in sample:
        reg = registrations[0]
        results.append({
            'name':    name,
            'display': reg.get('display_name', ' '.join(w.capitalize() for w in name.split())),
            'url':     reg.get('url', ''),
            'count':   len(registrations),
        })
    return results


# ── Stable ────────────────────────────────────────────────────────────────────

def load_stable() -> List[Dict]:
    # One-time migration: rename pasture.json → stable.json
    if not os.path.exists(STABLE_FILE) and os.path.exists(_PASTURE_LEGACY):
        try:
            os.rename(_PASTURE_LEGACY, STABLE_FILE)
        except Exception:
            pass
    if not os.path.exists(STABLE_FILE):
        return []
    try:
        with open(STABLE_FILE) as f:
            return json.load(f).get('horses', [])
    except Exception:
        return []


def save_stable(horses: List[Dict]):
    try:
        with open(STABLE_FILE, 'w') as f:
            json.dump({'horses': horses, 'updated': time.time()}, f)
    except Exception as e:
        print(f"Stable save error: {e}")


def add_to_stable(name: str, display: str, url: str, remaining: int = 1) -> List[Dict]:
    horses = load_stable()
    existing = next((h for h in horses if h['name'] == name), None)
    if existing:
        existing['remaining'] = remaining
    else:
        horses.append({'name': name, 'display': display, 'url': url, 'remaining': remaining})
    save_stable(horses)
    return horses


def remove_from_stable(name: str) -> List[Dict]:
    horses = [h for h in load_stable() if h['name'] != name]
    save_stable(horses)
    return horses


def clear_stable():
    save_stable([])


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