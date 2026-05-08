# horse-counter backlog

## Fixes

- **Tumblr post CSS desync** — New posts render as plain links with no tile styling; old posts still look correct. Root cause narrowed: `matcher.py:441` generates `class="horse-link coat-{coat}"` correctly, so the class is in the HTML sent to Tumblr — but Tumblr appears to be stripping the `class` attribute on ingestion. The `--bg`/`--fg` CSS vars are already inlined so colours survive, but the structural styling (`.horse-link`, `::before`/`::after` for legs/body shape) depends on the class. Fix: move the structural `.horse-link` rules from the Tumblr theme's `<style>` block into per-element inline styles, or use a `data-horse` attribute selector instead of a class (Tumblr may allow data attributes). Confirm by inspecting the raw HTML of a recently posted Tumblr post to verify whether the class is present or stripped.

## Tools

- **Link validator for short-names-validation.html (and eventually the full dictionary)** — pedigreequery.com sits behind Cloudflare, so plain HTTP requests (even with browser User-Agent) get a JS challenge page instead of the real response. HEAD requests are blocked outright (403). There's no lightweight signal to distinguish a valid horse page from a "not found" page without executing the Cloudflare challenge.

  Viable approach: use Playwright (or similar headless browser) with a single long-lived browser session that passes the initial Cloudflare challenge interactively, then reuses the resulting cookies for subsequent requests. The actual "not found" signal from pedigreequery is a page-content check (look for a phrase like "no horse found" or the registration prompt) rather than an HTTP status code. Key constraints:
  - Rate limit aggressively — 1 req/sec or slower, randomized delay
  - Run in batches (the short-names list is 1362 horses; the full dictionary is ~2M)
  - Start with the short-names list as a pilot
  - Output: annotated version of short-names-validation.html with a pass/fail badge per row, or a separate CSV of bad URLs
  - Could be a standalone script (`validate_links.py`) that writes results to `data/link_validation.json`

## Infrastructure

- **Sync horse_overrides.json from PA back to GitHub** — The canonical overrides file (deletes + corrections to the dictionary) lives on the PA server and gets edited in production. Changes don't automatically flow back to the repo, so a fresh deploy would regress them. Options: a one-click admin export/download, a cron that commits the file, or a deploy hook that pulls it first.

## Features

- **Ambient background horses** — A few horse chips rendered in the SVG grass background behind all working areas (z-indexed so they never overlap the UI). Bonus: simple walk cycle animation that lets them slowly wander around.

- **Public poem gallery + local save (PA website)** — Poems can be saved locally in addition to (or instead of) being pushed to Tumblr. Managed separately via the PA admin interface. Public-facing gallery page shows each poem rendered as horses standing in a field with title and attribution at the top. Horses slowly random-walk; a button resets them to their original positions; a toggle disables all movement.

- **Real coat color — encode standard notation first** — PedigreeQuery uses standard equine color notation (e.g. "b" = bay, "ch" = chestnut, "gr/ro" = grey/roan, "blk" = black, "b/br" = brown, "ro" = roan, "pal" = palomino, etc.). Build a mapping from these abbreviations to chip colors (bg/fg CSS vars) so the system is ready to consume scraped data without further work. Mass scrape comes later; hash-based color remains the fallback for horses with no data on record. Black Beauty shouldn't be brown.

## Recently completed

- Rhyme + thesaurus search modes in poetry builder — done (Datamuse API, two-phase chip UI, grouped results with per-group expand, stable rename)
- Famous horse recognition with special gold crown styling and tag injection — done
- Random horse button in poetry maker — done
- Pasture multi-horse count (drag N times for a horse with N registrations) — done
- Horse tile legs missing in Tumblr theme — fixed
- Drag ghost chip styling (was reverting to plain yellow) — fixed
