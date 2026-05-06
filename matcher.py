"""
matcher.py - Horse name matching engine

Key behaviours:
- Loads either the new rich dictionary (data/horses.json.gz) or the legacy
  compressed index (horses_compressed.json.gz) transparently.
- A single ChainCounter tracks how many times each name has been seen across
  the entire reblog chain so linking is globally consistent, not per-post.
- The Nth occurrence of a name uses registration[N-1]; occurrences beyond the
  registration count are left as plain text.
- Image markers ([[[IMAGE]]] / [[[IMAGE_DESC:...]]] ) are preserved through
  detection and only replaced during final HTML rendering.
"""

import re
import os
import json
import gzip
import urllib.parse
from typing import List, Dict, Optional, Tuple
from collections import defaultdict


# ── Dictionary loading ────────────────────────────────────────────────────────

class HorseDictionary:
    """
    Loads and exposes horse name data.

    Supports two on-disk formats:

    RICH format (data/horses.json.gz):
    {
      "word_index": { "first_word": ["full normalized name", ...] },
      "horses": {
        "northern dancer": {
          "registrations": [
            {"id": "...", "display_name": "Northern Dancer",
             "registry": "jockey_club_ca", "country": "CA",
             "birth_year": 1961, "url": "https://..."},
            ...
          ]
        }
      }
    }

    LEGACY format (horses_compressed.json.gz) — existing file:
    {
      "word_index": { "first_word": ["full normalized name", ...] },
      "all_horses": ["name1", "name2", ...]
    }

    Both are normalised to the same internal structure at load time so the
    rest of the app never needs to know which format is in use.
    """

    def __init__(self, rich_path: str, legacy_path: str, overrides_path: str = None):
        self.word_index: Dict[str, List[str]] = {}
        # name → list of registration dicts
        self.horses: Dict[str, List[Dict]] = {}
        self.max_word_length = 15
        self.loaded = False
        self.source = None
        self._rich_path = rich_path
        self._overrides_path = overrides_path

        if os.path.exists(rich_path):
            self._load_rich(rich_path)
        elif os.path.exists(legacy_path):
            self._load_legacy(legacy_path)
        else:
            print("ERROR: No horse dictionary found.")

        if overrides_path:
            self._apply_overrides()

    def _load_rich(self, path: str):
        try:
            print(f"Loading rich dictionary from {path}...")
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                data = json.load(f)
            self.word_index = data['word_index']
            self.horses = data['horses']
            self.loaded = True
            self.source = 'rich'
            print(f"Loaded {len(self.horses)} horses (rich format)")
        except Exception as e:
            print(f"Rich dictionary load error: {e}")

    def _load_legacy(self, path: str):
        try:
            print(f"Loading legacy dictionary from {path}...")
            try:
                with gzip.open(path, 'rt', encoding='utf-8') as f:
                    data = json.load(f)
            except gzip.BadGzipFile:
                print("  (file is plain JSON despite .gz extension, reading directly)")
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            self.word_index = data['word_index']
            # Convert flat list to rich structure with a single registration
            # URL uses the same PedigreeQuery construction as before
            self.horses = {}
            for name in data.get('all_horses', []):
                url = (
                    "https://www.pedigreequery.com/"
                    + urllib.parse.quote(name.replace(' ', '+'))
                )
                self.horses[name] = [
                    {
                        "id": name,
                        "display_name": _title_case(name),
                        "registry": "pedigreequery",
                        "country": None,
                        "birth_year": None,
                        "url": url,
                    }
                ]
            self.loaded = True
            self.source = 'legacy'
            print(f"Loaded {len(self.horses)} horses (legacy format)")
        except Exception as e:
            print(f"Legacy dictionary load error: {e}")

    def _apply_overrides(self):
        if not self._overrides_path or not os.path.exists(self._overrides_path):
            return
        try:
            with open(self._overrides_path, 'r', encoding='utf-8') as f:
                overrides = json.load(f)
        except Exception as e:
            print(f"Overrides load error: {e}")
            return
        for name in overrides.get('delete', []):
            self._remove_from_index(name)
        for name, regs in overrides.get('set', {}).items():
            self._add_to_index(name, regs)
        nd = len(overrides.get('delete', []))
        ns = len(overrides.get('set', {}))
        if nd or ns:
            print(f"Overrides applied: {nd} deletions, {ns} sets")

    def _remove_from_index(self, name: str):
        if name in self.horses:
            del self.horses[name]
        first = name.split()[0] if name else name
        if first in self.word_index:
            self.word_index[first] = [n for n in self.word_index[first] if n != name]
            if not self.word_index[first]:
                del self.word_index[first]

    def _add_to_index(self, name: str, regs: List[Dict]):
        self.horses[name] = regs
        first = name.split()[0] if name else name
        if first not in self.word_index:
            self.word_index[first] = []
        if name not in self.word_index[first]:
            self.word_index[first].append(name)

    def _read_overrides(self) -> dict:
        if self._overrides_path and os.path.exists(self._overrides_path):
            try:
                with open(self._overrides_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {'delete': [], 'set': {}}

    def _write_overrides(self, overrides: dict):
        with open(self._overrides_path, 'w', encoding='utf-8') as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)

    def override_delete(self, name: str):
        """Remove a name from the live dictionary and persist the deletion."""
        self._remove_from_index(name)
        if not self._overrides_path:
            return
        overrides = self._read_overrides()
        # Remove from set if it was there
        overrides.setdefault('set', {}).pop(name, None)
        # Add to delete list (deduplicated)
        delete_list = overrides.setdefault('delete', [])
        if name not in delete_list:
            delete_list.append(name)
        self._write_overrides(overrides)

    def override_set(self, name: str, regs: List[Dict]):
        """Add or replace a name in the live dictionary and persist the change."""
        self._add_to_index(name, regs)
        if not self._overrides_path:
            return
        overrides = self._read_overrides()
        # Remove from delete list if present (set wins)
        delete_list = overrides.setdefault('delete', [])
        if name in delete_list:
            delete_list.remove(name)
        overrides.setdefault('set', {})[name] = regs
        self._write_overrides(overrides)

    def registrations_for(self, normalized_name: str) -> List[Dict]:
        return self.horses.get(normalized_name, [])

    def name_exists(self, normalized_name: str) -> bool:
        return normalized_name in self.horses


def _title_case(name: str) -> str:
    """Simple title-case that handles apostrophes sensibly."""
    return ' '.join(w.capitalize() for w in name.split())


# ── Chain-level occurrence counter ───────────────────────────────────────────

class ChainCounter:
    """
    Tracks how many times each horse name has been seen across the full chain.
    Call .next_registration(name) to get the next unused registration for that
    name, or None if all registrations are exhausted.
    """

    def __init__(self, dictionary: HorseDictionary):
        self.dictionary = dictionary
        self._counts: Dict[str, int] = defaultdict(int)

    def next_registration(self, normalized_name: str) -> Optional[Dict]:
        regs = self.dictionary.registrations_for(normalized_name)
        idx = self._counts[normalized_name]
        self._counts[normalized_name] += 1
        if idx < len(regs):
            return regs[idx]
        return None  # name seen more times than registrations exist

    def total_linked(self) -> int:
        """Count of occurrences that received a registration (got a link)."""
        total = 0
        for name, count in self._counts.items():
            regs = self.dictionary.registrations_for(name)
            total += min(count, len(regs))
        return total

    def total_seen(self) -> int:
        return sum(self._counts.values())


# ── Text normalisation ────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"['\"`]", "", text)
    text = re.sub(r"[-_]", " ", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


# ── Core matching ─────────────────────────────────────────────────────────────

def find_horses_in_text(
    text: str,
    dictionary: HorseDictionary,
) -> List[Dict]:
    """
    Find horse name matches in text.
    Returns list of match dicts with keys:
        name (normalized), original (as found), start, end
    Does NOT assign registrations — that is the ChainCounter's job.
    Skips matches inside [[[IMAGE]]] / [[[IMAGE_DESC:...]]] marker prefixes.
    """
    if not text or not dictionary.word_index:
        return []

    if len(text) > 50_000:
        return _batch_find(text, dictionary)
    return _find_in_chunk(text, 0, dictionary)


def _batch_find(text: str, dictionary: HorseDictionary) -> List[Dict]:
    chunk_size = 20_000
    overlap    = 500
    seen: set  = set()
    all_matches: List[Dict] = []

    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i:i + chunk_size]
        for m in _find_in_chunk(chunk, i, dictionary):
            key = (m['start'], m['end'])
            if key not in seen:
                seen.add(key)
                all_matches.append(m)

    all_matches.sort(key=lambda x: x['start'])
    return all_matches



def _find_in_chunk(
    text: str, offset: int, dictionary: HorseDictionary
) -> List[Dict]:
    normalized = normalize_text(text)
    words = normalized.split()
    if not words:
        return []

    found: List[Dict] = []
    used: set = set()
    max_len = min(dictionary.max_word_length, len(words))

    for length in range(max_len, 0, -1):
        for i in range(len(words) - length + 1):
            phrase = " ".join(words[i:i + length])
            first_word = words[i]

            if first_word not in dictionary.word_index:
                continue
            if phrase not in dictionary.word_index[first_word]:
                continue

            # Find the first occurrence of this phrase not overlapping used positions
            match = _find_first_free_position(text, phrase, used)
            if not match:
                continue

            start, end, original = match
            if _is_in_marker_prefix(text, start, end):
                continue

            found.append({
                'name': phrase,
                'original': original,
                'start': offset + start,
                'end': offset + end,
            })
            used.update(range(start, end))

    return found


def _find_first_free_position(
    text: str, phrase: str, used: set
) -> Optional[Tuple[int, int, str]]:
    """
    Find the first occurrence of phrase in text whose character positions
    do not overlap with the already-used set.
    Uses finditer so repeated names like "demon dance demon dance" correctly
    claim the second occurrence when the first is already taken.
    """
    try:
        words = phrase.split()
        parts = [r"[\'\`]*" + re.escape(w) + r"[\'\`]*" for w in words]
        pattern = r'\b' + r'[\s\-_]+'.join(parts) + r'\b'
        for m in re.finditer(pattern, text, re.IGNORECASE):
            pos_range = set(range(m.start(), m.end()))
            if not pos_range & used:
                return m.start(), m.end(), text[m.start():m.end()]
    except Exception:
        pass
    return None




def _is_in_marker_prefix(text: str, start: int, end: int) -> bool:
    """
    Return True if the match at [start:end] is inside the marker keyword
    part of [[[IMAGE]]] or [[[IMAGE_DESC:...]]] (i.e. before the colon).
    Matches inside the alt-text (after the colon) are fine.
    """
    horse_text = text[start:end]
    if horse_text in {'IMAGE', 'IMAGE_DESC', 'GIF', 'GIF_DESC', 'VIDEO', 'DESC'}:
        return True
    if '[[[' in horse_text or ']]]' in horse_text:
        return True

    last_open = text[:start].rfind('[[[')
    if last_open == -1:
        return False

    close = text.find(']]]', last_open)
    if close == -1 or close < end:
        return False

    # Inside a marker — check whether we're before or after the colon
    marker_section = text[last_open:start]
    return ':' not in marker_section


# ── Horse tile appearance ─────────────────────────────────────────────────────

_COATS = [
    ('#7a3520', '#f5ecd7'),  # bay
    ('#1c1c1c', '#e8d5b0'),  # black
    ('#7a7a7a', '#f0ead6'),  # dapple grey
    ('#8b3a1f', '#fae8c8'),  # chestnut
    ('#c8961a', '#2a1800'),  # palomino
    ('#c8bfaa', '#1c1008'),  # grey/white
    ('#4a2812', '#ead8b8'),  # liver
    ('#8a6a5a', '#f0e4d0'),  # roan
]

def _tile_appearance(name: str) -> Tuple[str, str, bool]:
    """Return (bg, fg, is_reversed) for a normalized horse name."""
    h = sum(ord(c) for c in name)
    bg, fg = _COATS[h % len(_COATS)]
    return bg, fg, h % 2 == 0


# ── HTML rendering ────────────────────────────────────────────────────────────

def render_chain_item(
    text: str,
    matches: List[Dict],
    counter: ChainCounter,
    famous=None,
) -> Tuple[str, int]:
    """
    Given the raw text of one chain item and its pre-found matches,
    consume registrations from the ChainCounter and return:
        (html_string, linked_word_count)

    Applies links in reverse-position order so indices stay valid,
    then replaces image markers, then wraps in paragraph tags.
    """
    linked_words = 0
    result = text

    # Sort matches by start position descending so replacements don't shift indices
    sorted_matches = sorted(matches, key=lambda x: x['start'], reverse=True)

    for m in sorted_matches:
        start, end = m['start'], m['end']
        if start >= len(result) or end > len(result):
            continue

        registration = counter.next_registration(m['name'])
        original_text = result[start:end]

        if registration:
            bg, fg, rev = _tile_appearance(m['name'])
            is_famous = famous is not None and famous.lookup(m['name']) is not None
            cls = 'horse-link'
            if rev:
                cls += ' rev'
            if is_famous:
                cls += ' famous-horse'
            crown = '<span class="famous-crown" aria-hidden="true">&#9812;</span>' if is_famous else ''
            link = (
                f'<a class="{cls}" href="{registration["url"]}"'
                f' style="--bg:{bg};--fg:{fg}">'
                f'<span class="legs"></span>{crown}{original_text}</a>'
            )
            linked_words += len(m['name'].split())
        else:
            link = original_text  # exhausted registrations — plain text

        result = result[:start] + link + result[end:]

    # Replace content markers
    result = result.replace('[[[IMAGE]]]', '[Image]')
    result = re.sub(r'\[\[\[IMAGE_DESC:(.*?)\]\]\]', r'[Image: \1]', result)
    result = result.replace('[[[GIF]]]', '[Animated GIF]')
    result = re.sub(r'\[\[\[GIF_DESC:(.*?)\]\]\]', r'[Animated GIF: \1]', result)
    result = result.replace('[[[VIDEO]]]', '[Video]')

    # Preserve formatting
    result = _preserve_formatting(result)
    return result, linked_words


def _preserve_formatting(text: str) -> str:
    """Convert newlines to HTML, wrap paragraphs."""
    if not text:
        return ""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    paragraphs = text.split('\n\n')
    parts = []
    for para in paragraphs:
        para = para.strip()
        if para:
            para = para.replace('\n', '<br>')
            parts.append(f'<p>{para}</p>')
    return ''.join(parts)


# ── Statistics ────────────────────────────────────────────────────────────────

def compute_stats(
    chain_texts: List[str],
    counter: ChainCounter,
) -> Dict:
    """
    chain_texts: list of raw (pre-linking) body strings from each chain item.
    Returns dict with total_words, linked_words, horse_density (0.0–1.0).
    """
    total_words = sum(len(t.split()) for t in chain_texts)
    linked_words = counter.total_linked()  # word count, not occurrence count

    # Recount linked words properly as sum of word-lengths of matched names
    # (counter.total_linked returns occurrence count; we need word count)
    # This is recalculated in render_chain so we accept a passed-in value too.

    density = linked_words / total_words if total_words > 0 else 0.0
    return {
        'total_words': total_words,
        'linked_words': linked_words,
        'horse_density': round(density * 100, 1),
    }