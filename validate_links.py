#!/usr/bin/env python3
"""
Validate pedigreequery URLs from the short-names dictionary.

For each horse URL, loads the page in a real Chromium session (to pass
Cloudflare), then checks the page content to distinguish a found horse
from a "not found" / registration-prompt page.

Output: data/link_validation.json  — {url: "ok" | "not_found" | "degenerate" | "cloudflare" | "error"}

Usage:
    python validate_links.py              # validate all short names
    python validate_links.py --resume     # skip already-checked URLs
    python validate_links.py --limit 20   # stop after N URLs (for testing)
"""

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE          = "https://www.pedigreequery.com"
RESULTS_FILE  = Path("data/link_validation.json")

# ── Signals ───────────────────────────────────────────────────────────────────
# Three outcome tiers:
#
#   not_found  — pedigreequery says the slug doesn't exist; offers to add it
#   degenerate — page resolves but the horse is listed as its own ancestor
#                (circular self-reference); "??? Research {name}" appears in
#                every ancestor slot, causing DI/CD to compute as Inf
#   ok         — real horse; may have unknown parentage (DI=Inf is fine if
#                the pedigree slots contain other horses, not itself)
#
NOT_FOUND_PHRASES = [
    "horse not found",
    "made a typo",
]

def classify_page(content: str, url: str) -> str:
    low = content.lower()
    if "just a moment" in low or "enable javascript and cookies" in low:
        return "cloudflare"
    for phrase in NOT_FOUND_PHRASES:
        if phrase in low:
            return "not_found"
    # Circular self-reference: pedigreequery puts a "Research" addrequest link
    # in each ancestor slot, pointing back to the horse's own slug. The slug
    # always appears once legitimately (edit link etc); more than once means
    # the horse is its own ancestor.
    slug = url.rstrip('/').split('/')[-1]
    if low.count(f'horse={slug}') > 1:
        return "degenerate"
    return "ok"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_results() -> dict:
    if RESULTS_FILE.exists():
        return json.loads(RESULTS_FILE.read_text())
    return {}

def save_results(results: dict):
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(results, indent=2, sort_keys=True))

def delay():
    t = random.uniform(2.0, 4.0)
    time.sleep(t)

def get_page_content(page, url: str, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            page.goto(url, wait_until="domcontentloaded")
            # Wait for Cloudflare to resolve — real pages have many links;
            # "not found" pages have at least a nav. Bail after 20s.
            page.wait_for_function(
                "() => document.querySelectorAll('a[href]').length > 5",
                timeout=20000,
            )
            return page.content()
        except PWTimeout:
            if attempt < retries - 1:
                print(f"    timeout, retrying ({attempt + 2}/{retries})…")
                time.sleep(random.uniform(3, 6))
            else:
                return None


# ── Source ────────────────────────────────────────────────────────────────────

def load_short_horses() -> list[dict]:
    """Return all horses with name length <= 3 from the live dictionary."""
    sys.path.insert(0, ".")
    from config import HORSES_RICH_FILE, HORSES_LEGACY_FILE, HORSE_OVERRIDES_FILE
    from matcher import HorseDictionary
    d = HorseDictionary(HORSES_RICH_FILE, HORSES_LEGACY_FILE, HORSE_OVERRIDES_FILE)
    horses = []
    for name, regs in d.horses.items():
        if len(name) <= 3:
            reg = regs[0]
            url = reg.get("url", "")
            if url:
                horses.append({"name": name, "display": reg.get("display_name", name), "url": url})
    horses.sort(key=lambda h: (len(h["name"]), h["name"]))
    return horses


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", help="Skip already-checked URLs")
    parser.add_argument("--limit",  type=int, default=0,  help="Stop after N checks (0 = no limit)")
    args = parser.parse_args()

    horses  = load_short_horses()
    results = load_results() if args.resume else {}

    todo = [h for h in horses if h["url"] not in results] if args.resume else horses
    if args.limit:
        todo = todo[:args.limit]

    print(f"{len(horses)} short-name horses total, {len(todo)} to check")
    if not todo:
        print("Nothing to do.")
        return

    counts = {"ok": 0, "not_found": 0, "degenerate": 0, "cloudflare": 0, "error": 0}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()

        for i, horse in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {horse['display']:<20} {horse['url']} … ", end="", flush=True)
            content = get_page_content(page, horse["url"])
            if content is None:
                status = "error"
            else:
                status = classify_page(content, horse["url"])
            counts[status] += 1
            results[horse["url"]] = status
            print(status)
            save_results(results)
            if i < len(todo):
                delay()

        browser.close()

    print(f"\nDone. {counts}")
    print(f"Results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
