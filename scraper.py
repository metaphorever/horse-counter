#!/usr/bin/env python3
"""
PedigreeQuery sitemap scraper.

Walk order:
  sitemap.php?A  →  lists 3-letter prefix codes (AAA, AAB, …)
  sitemap.php?AAA →  lists horse links for that prefix

Output:  data/scrape/horses.jsonl   (one JSON object per line)
Progress: data/scrape/progress.json  (resume-safe — skip completed prefixes)

Setup:
    pip install playwright beautifulsoup4
    playwright install chromium
    python scraper.py
"""

import json
import time
import random
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE        = "https://www.pedigreequery.com"
DATA_DIR    = Path("data/scrape")
HORSES_FILE = DATA_DIR / "horses.jsonl"
PROGRESS    = DATA_DIR / "progress.json"
LETTERS     = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_progress():
    if PROGRESS.exists():
        p = json.loads(PROGRESS.read_text())
        p["completed"] = set(p.get("completed", []))
        return p
    return {"completed": set(), "prefixes": []}

def save_progress(p):
    PROGRESS.write_text(json.dumps(
        {"completed": sorted(p["completed"]), "prefixes": p["prefixes"]},
        indent=2
    ))

def delay():
    t = random.uniform(2.5, 5.0)
    time.sleep(t)

def get_html(page, url, retries=3):
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded")
            # Wait until real page content loads (Cloudflare challenge resolves)
            page.wait_for_function(
                "() => document.querySelectorAll('a[href]').length > 10",
                timeout=25000,
            )
            return page.content()
        except PWTimeout:
            if attempt < retries - 1:
                print(f"    timeout, retrying ({attempt + 2}/{retries})…")
                time.sleep(random.uniform(4, 8))
            else:
                print(f"    FAILED: {url}")
                return None

# ── Parsers ───────────────────────────────────────────────────────────────────

def extract_prefixes(html):
    """Return list of 3-letter prefix codes from a letter index page."""
    soup = BeautifulSoup(html, "html.parser")
    codes = []
    for a in soup.find_all("a", href=True):
        m = re.match(r"^sitemap\.php\?([A-Z]{3})$", a["href"])
        if m:
            codes.append(m.group(1))
    return codes

def is_horse_href(href):
    """True if href looks like a horse slug, not a nav/asset link."""
    if not href.startswith("/"):
        return False
    path = href[1:]
    if not path or "/" in path:        # empty or has subdirectory
        return False
    # Exclude file extensions and known nav slugs
    if re.search(r"\.(php|css|js|gif|png|jpg)$", path):
        return False
    return True

def extract_horses(html):
    """Return list of {name, url} dicts from a prefix page."""
    soup = BeautifulSoup(html, "html.parser")
    horses = []
    for a in soup.find_all("a", href=True):
        if not is_horse_href(a["href"]):
            continue
        name = a.get_text(strip=True)
        if not name:
            continue
        slug = a["href"][1:]                          # strip leading /
        url  = f"{BASE}/{slug}"
        horses.append({"name": name.lower(), "url": url})
    return horses

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,   # keeps Cloudflare happy
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        # ── Phase 1: discover all prefix codes (26 requests) ─────────────────
        if not progress["prefixes"]:
            print("Phase 1: discovering prefix codes…")
            for letter in LETTERS:
                url  = f"{BASE}/sitemap.php?{letter}"
                print(f"  {letter}  {url}")
                html = get_html(page, url)
                if html:
                    codes = extract_prefixes(html)
                    progress["prefixes"].extend(codes)
                    print(f"     → {len(codes)} prefixes")
                    save_progress(progress)
                delay()
            print(f"  Total prefixes discovered: {len(progress['prefixes'])}\n")

        # ── Phase 2: scrape each prefix page ─────────────────────────────────
        remaining = [c for c in progress["prefixes"] if c not in progress["completed"]]
        total     = len(progress["prefixes"])
        done      = len(progress["completed"])
        print(f"Phase 2: {done}/{total} done, {len(remaining)} remaining\n")

        with HORSES_FILE.open("a") as out:
            for code in remaining:
                url  = f"{BASE}/sitemap.php?{code}"
                done = len(progress["completed"])
                print(f"[{done + 1}/{total}] {code}  ", end="", flush=True)

                html = get_html(page, url)
                if html:
                    horses = extract_horses(html)
                    for h in horses:
                        out.write(json.dumps(h) + "\n")
                    out.flush()
                    print(f"→ {len(horses)} horses")
                else:
                    print("→ skipped")

                progress["completed"].add(code)
                save_progress(progress)
                delay()

        browser.close()

    total_lines = sum(1 for _ in HORSES_FILE.open())
    print(f"\nDone. {total_lines:,} horse records written to {HORSES_FILE}")


if __name__ == "__main__":
    main()
