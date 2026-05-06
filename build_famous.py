#!/usr/bin/env python3
"""
build_famous.py - Build data/famous_horses.json from race winner CSVs.

Add new races by placing a CSV of winner names (one per line, no header)
in data/ and adding an entry to RACE_FILES below.

Run: python3 build_famous.py
"""

import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))

# Map (csv filename, race display name) — order matters: first entry wins display_name
RACE_FILES = [
    ('KD-Winners.csv', 'Kentucky Derby'),
]


def normalize(name: str) -> str:
    name = name.lower()
    name = re.sub(r"['\"`]", "", name)
    name = re.sub(r"[-_]", " ", name)
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


horses: dict = {}

for filename, race_name in RACE_FILES:
    path = os.path.join(BASE, 'data', filename)
    if not os.path.exists(path):
        print(f"  Missing: {path}")
        continue
    with open(path, encoding='utf-8') as f:
        names = [line.strip() for line in f if line.strip()]

    winner_tag = f"{race_name} Winner"
    added = 0
    for display in names:
        key = normalize(display)
        if not key:
            continue
        if key not in horses:
            horses[key] = {'display': display, 'races': [], 'tags': []}
            added += 1
        if race_name not in horses[key]['races']:
            horses[key]['races'].append(race_name)
        if winner_tag not in horses[key]['tags']:
            horses[key]['tags'].append(winner_tag)
        if display not in horses[key]['tags']:
            horses[key]['tags'].append(display)

    print(f"  {filename}: {len(names)} names ({added} new keys)")

out = os.path.join(BASE, 'data', 'famous_horses.json')
with open(out, 'w', encoding='utf-8') as f:
    json.dump(horses, f, indent=2, ensure_ascii=False)
print(f"Wrote {len(horses)} famous horses to {out}")
