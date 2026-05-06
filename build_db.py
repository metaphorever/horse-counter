#!/usr/bin/env python3
"""
Build horses.json.gz from scraped horses.jsonl.

Reads:  data/scrape/horses.jsonl
Writes: data/horses.json.gz  (replaces existing)

The output format matches what matcher.py's HorseDictionary expects:
  {
    "word_index": { "first_word": ["full normalized name", ...] },
    "horses":     { "normalized name": [{"url": "..."}, ...] }
  }

Multiple entries with the same normalized name (e.g. das+kapital and
das+kapital2) are stored as separate registrations under the same key,
so ChainCounter can link each occurrence of the name to a different horse.
"""

import gzip
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HORSES_FILE = Path("data/scrape/horses.jsonl")
FLAGGED_FILE = Path("data/scrape/flagged.txt")
OUTPUT_FILE = Path("data/horses.json.gz")

# Valid PQ slug characters: lowercase letters, digits, + (space), - (dash in name)
VALID_SLUG = re.compile(r"^[a-z0-9+\-]+$")

# Data-entry errors: two identical groups separated by a comma e.g. "fq,fq", "fi,fi"
REPEATED_COMMA = re.compile(r"^([a-z]+),\1$")


def normalize(text: str) -> str:
    """Mirror of matcher.normalize_text — must stay in sync."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"['\"`]", "", text)
    text = re.sub(r"[-_]", " ", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def build():
    if not HORSES_FILE.exists():
        print(f"ERROR: {HORSES_FILE} not found. Run scraper.py first.")
        sys.exit(1)

    print(f"Reading {HORSES_FILE}…")
    grouped: dict[str, list[str]] = defaultdict(list)
    flagged = []
    skipped = 0
    total   = 0

    with HORSES_FILE.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            record = json.loads(line)
            key = normalize(record.get("name", ""))
            url = record.get("url", "")
            if not key or not url:
                skipped += 1
                continue

            # Flag repeated-comma data errors e.g. "fq,fq" (slug looks clean but name is bad)
            raw_name = record.get("name", "")
            if REPEATED_COMMA.match(raw_name):
                flagged.append(f"{url}  (name: {raw_name})")
                skipped += 1
                continue

            # Flag slugs with characters outside a-z 0-9 + -
            slug = url.split("/")[-1]
            if not VALID_SLUG.match(slug):
                flagged.append(f"{url}  (name: {raw_name})")
                skipped += 1
                continue

            # Avoid exact duplicate URLs under the same name
            if url not in grouped[key]:
                grouped[key].append(url)

    if flagged:
        FLAGGED_FILE.write_text("\n".join(flagged) + "\n")
        print(f"  Flagged {len(flagged):,} suspect entries → {FLAGGED_FILE}")

    print(f"  {total:,} lines → {len(grouped):,} unique normalized names  ({skipped} skipped)")

    # Build horses dict: name → list of {url} registrations
    horses = {name: [{"url": u} for u in urls] for name, urls in grouped.items()}

    # Build word_index: first word → list of full names starting with it
    # (used by matcher._find_in_chunk for fast candidate lookup)
    word_index: dict[str, list[str]] = defaultdict(list)
    for name in horses:
        first = name.split()[0] if name.split() else name
        word_index[first].append(name)

    # max word length — used by matcher to cap phrase search
    max_words = max((len(n.split()) for n in horses), default=1)
    print(f"  Longest name: {max_words} words")

    data = {
        "word_index": dict(word_index),
        "horses":     horses,
    }

    print(f"Writing {OUTPUT_FILE}…")
    with gzip.open(OUTPUT_FILE, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)

    size_mb = OUTPUT_FILE.stat().st_size / 1_000_000
    print(f"Done. {len(horses):,} horses, {size_mb:.1f} MB compressed")
    print(f"Note: update HorseDictionary.max_word_length to {max_words} in matcher.py if needed")


if __name__ == "__main__":
    build()
