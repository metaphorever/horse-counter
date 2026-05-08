#!/usr/bin/env python3
"""
Bulk-delete horse names from the PA dictionary via the admin API.

Reads a plain text file of horse names (one per line, # comments ignored)
and posts each to /admin/dictionary/delete on the target site.

Usage:
    python tools/bulk_delete.py tools/short-names-deletions.txt
    python tools/bulk_delete.py tools/short-names-deletions.txt --url https://yoursite.pythonanywhere.com
    python tools/bulk_delete.py tools/short-names-deletions.txt --dry-run

Auth:
    The script logs in using your admin PIN. Set it via the PA_PIN environment
    variable or enter it interactively when prompted:

        PA_PIN=yourpin python tools/bulk_delete.py tools/short-names-deletions.txt

    The session cookie is reused across all requests in a single run.

Input file format:
    One horse name per line. Anything after # is a comment and is ignored.
    Blank lines are skipped. Example:

        abc   # not_found
        an    # degenerate
        avo   # degenerate — horse is its own ancestor
"""

import argparse
import os
import sys
import time
import getpass
import requests


DEFAULT_URL = "https://horsecounterbot.pythonanywhere.com"


def load_names(path: str) -> list[str]:
    names = []
    with open(path) as f:
        for raw in f:
            line = raw.split("#")[0].strip()
            if line:
                names.append(line)
    return names


def login(session: requests.Session, base_url: str, pin: str) -> bool:
    r = session.post(
        f"{base_url}/login",
        data={"pin": pin},
        allow_redirects=True,
        timeout=15,
    )
    return r.ok and "/login" not in r.url


def delete_horse(session: requests.Session, base_url: str, name: str) -> bool:
    r = session.post(
        f"{base_url}/admin/dictionary/delete",
        data={"name": name, "q": name},
        allow_redirects=True,
        timeout=15,
    )
    return r.ok


def main():
    parser = argparse.ArgumentParser(description="Bulk-delete horses from the PA dictionary.")
    parser.add_argument("names_file", help="Text file of horse names to delete")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Base URL of the site (default: {DEFAULT_URL})")
    parser.add_argument("--dry-run", action="store_true", help="Print names without posting")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between requests (default: 0.5)")
    args = parser.parse_args()

    names = load_names(args.names_file)
    if not names:
        print("No names found in file.")
        sys.exit(1)

    print(f"{len(names)} names to delete from {args.url}")

    if args.dry_run:
        for name in names:
            print(f"  [dry-run] would delete: {name}")
        return

    pin = os.environ.get("PA_PIN") or getpass.getpass("Admin PIN: ")

    session = requests.Session()
    session.headers["User-Agent"] = "horse-counter-bulk-delete/1.0"

    print("Logging in…")
    if not login(session, args.url, pin):
        print("Login failed. Check your PIN and URL.")
        sys.exit(1)
    print("Logged in.\n")

    ok = failed = 0
    for i, name in enumerate(names, 1):
        print(f"[{i}/{len(names)}] {name:<25}", end="", flush=True)
        success = delete_horse(session, args.url, name)
        if success:
            ok += 1
            print("deleted")
        else:
            failed += 1
            print("FAILED")
        if i < len(names):
            time.sleep(args.delay)

    print(f"\nDone. {ok} deleted, {failed} failed.")


if __name__ == "__main__":
    main()
