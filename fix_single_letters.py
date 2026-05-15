#!/usr/bin/env python3
"""One-off fix: remove bad single-letter dictionary entries, replace valid ones."""
import gzip, json, shutil
from pathlib import Path

DATA = Path("data/horses.json.gz")
BACKUP = Path("data/horses_pre_singlefix.json.gz")

VALID = {
    "i": [{"url": "https://www.pedigreequery.com/i2"}],
    "n": [{"url": "https://www.pedigreequery.com/n2"}],
    "v": [{"url": "https://www.pedigreequery.com/v2"}],
    "x": [{"url": "https://www.pedigreequery.com/x2"}],
}

with gzip.open(DATA) as f:
    db = json.load(f)

singles_before = {k: v for k, v in db["horses"].items() if len(k) == 1}
print(f"Single-letter entries before: {sorted(singles_before.keys())}")

# Remove all single-letter entries
for k in list(singles_before.keys()):
    del db["horses"][k]
    # Clean word_index: remove this name from the first-word bucket
    if k in db["word_index"]:
        db["word_index"][k] = [n for n in db["word_index"][k] if n != k]
        if not db["word_index"][k]:
            del db["word_index"][k]

# Add back the valid ones
for letter, regs in VALID.items():
    db["horses"][letter] = regs
    if letter not in db["word_index"]:
        db["word_index"][letter] = []
    if letter not in db["word_index"][letter]:
        db["word_index"][letter].append(letter)

singles_after = {k: v for k, v in db["horses"].items() if len(k) == 1}
print(f"Single-letter entries after:  {sorted(singles_after.keys())}")
for k, v in sorted(singles_after.items()):
    print(f"  {k!r}: {v}")

shutil.copy(DATA, BACKUP)
print(f"\nBackup written to {BACKUP}")

with gzip.open(DATA, "wt", encoding="utf-8") as f:
    json.dump(db, f, ensure_ascii=False)

print(f"Done. {DATA} rewritten.")
