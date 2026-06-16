# Phase 2.2 — Bluesky cross-post connector (multi-target poem queue)

**Model:** Opus · **Effort:** high
**Depends on:** 1.20 (cross-post queue) · cross-post research (2026-05-25)
**Status:** spec — awaiting Clover confirmation before build

---

## Problem

The poem cross-post queue (Phase 1.20) dispatches to **Tumblr only**, with three
Tumblr-specific actions (post / queue / draft). We want **Bluesky as a second
target**, funnel-to-site (short hook + one permalink card), without duplicating
the per-platform workflow that made the original design heavy.

The simplification: collapse the *poem* dispatch to a **single "Crosspost"
action** that fires every connected platform live, and track only a tiny
per-platform **result** so a partial failure is retryable. Draft/queue modes for
poems are dropped (decided with Clover — funnel-to-site posts are auto-generated,
nothing to hand-tweak).

---

## Decisions (resolved with Clover)

1. **Two targets, both kept.** Tumblr + Bluesky. Poem path is **direct live
   posting only** — no draft, no platform queue.
2. **The "count horses in text" feature is OUT OF SCOPE and untouched.** Its
   Tumblr post/queue/draft capability (the `submit_post(action=…)` selector,
   `queue_handler.py`) stays exactly as-is for the future counter revamp. Only
   the *poem* dispatch path changes; it simply always calls Tumblr with
   `action='post'`.
3. **Text + link-card now.** Image cards deferred to the Playwright work (a
   cross-post research prerequisite that needs Jon/root on the VPS first).
4. **Account:** handle **`poethorse.bsky.social`**, app password lives only
   in the VPS env as `BLUESKY_APP_PASSWORD` — never in the repo or chat.

---

## Risk resolved

1.20's ROADMAP note said the Tumblr dispatch was never *logged* as verified, but
**Clover confirms it works in practice — has cross-posted to Tumblr many times.**
So the base path is sound; Bluesky is being added on a known-good dispatch.

---

## Data model

`crosspost_queue` today: `id, poem_id UNIQUE, status, queued_at, posted_at`
(single-target).

**Change — add two nullable per-platform result columns:**

| column           | values                                      |
|------------------|---------------------------------------------|
| `tumblr_status`  | `NULL` (fresh) → `posted` / `failed` / `skipped` |
| `bluesky_status` | `NULL` (fresh) → `posted` / `failed` / `skipped` |

Migration via the existing unversioned pattern (`_COLUMN_MIGRATIONS` +
`apply_migrations()` in `db/seed.py`, `ALTER TABLE … ADD COLUMN`). The legacy
`status` / `posted_at` columns are left in place (harmless) but no longer drive
the queue.

**Pending rule** (what `get_pending` returns):

```
pending  ⇔  NOT ( tumblr_status  IN ('posted','skipped')
              AND bluesky_status IN ('posted','skipped') )
```

- Fresh item: both `NULL` → pending.
- One platform `failed`: still pending → "Crosspost" retries only the
  unfinished platform(s).
- A platform that is **not connected** at dispatch time is marked `skipped`
  for that item, so a single-platform setup still resolves cleanly.
- Fully resolved (`posted`/`skipped` on both) → drops out of the queue.

Two columns is the deliberate stopping point for two platforms (see complexity
note). A third platform (Mastodon, per research) is what graduates this to a
normalized `crosspost_targets(queue_id, platform, status, …)` child table — not
before.

---

## Connector — `bluesky.py` (new)

- Library: **`atproto`** (PyPI, pure-Python — no system libs, unlike Playwright;
  `pip install` only). Add to `requirements.txt`.
- `BlueskyManager` class, shaped like `TumblrManager` (auth.py) for consistency:
  - `authenticated` property — true iff `BLUESKY_HANDLE` + `BLUESKY_APP_PASSWORD`
    are both set (and, after first use, login succeeded).
  - lazy login: `Client().login(handle, app_password)`; cache the client at
    module scope. At our volume (≤1 post/poem, manual), re-login per dispatch is
    also acceptable — cache, fall back to re-login on session error.
  - `post_poem(text, link_url, link_title, link_desc) -> (success, err)` —
    builds a post with an **external embed (link card)** pointing at the poem
    permalink. No thumbnail for now (image-card work adds `og:image` later).

## Post content (funnel-to-site)

Bluesky post = short text hook + a link card to `https://poet.horse/p/<short>`.

- **Text** (≤300 chars; the card URL does **not** count, but keep text tight):
  ```
  "{title}" a poem of {count} horse{plural} by {author}
  ```
  e.g. `"Aubade for a Paddock" a poem of 7 horses by Clover`
  - Untitled → drop the quoted-title clause: `A poem of 7 horses by Clover`.
  - Anonymous → drop the `by {author}` clause.
  - `{plural}` = `s` unless count is 1.
- **Card:** `uri` = permalink, `title` = poem title or `A poem on poet.horse`,
  `description` = a short preview (e.g. first line's horse names). We control the
  page, so card fields are built directly — no OG scraping needed.
- Bare URL is **not** duplicated in the text (the card carries it) — cleaner hook.

---

## Admin UI — `templates/admin_crosspost_queue.html`

- Replace the three Tumblr buttons (`Add to Tumblr queue` / `Post now` /
  `Save as draft`) with **one `Crosspost` button** per item →
  `POST /admin/crosspost-queue/<id>/dispatch` (no `action` field).
- Per-item **status row**: `Tumblr ✓ / ✗ / —`   `Bluesky ✓ / ✗ / —`
  (`—` = skipped/not-connected, `✗` = failed → retry available).
- Connection banners for **both** platforms: Tumblr (`/auth` link as today),
  Bluesky (env-configured → "connected" / "set BLUESKY_HANDLE +
  BLUESKY_APP_PASSWORD" if missing).
- `Skip` button unchanged in spirit — marks the item resolved (both platforms
  `skipped`).
- "Crosspost" on a partially-failed item retries only platforms not already
  `posted`.

---

## Backend changes (summary)

- **`config.py`** — `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` from env.
- **`bluesky.py`** (new) — `BlueskyManager` + `post_poem`.
- **`db/seed.py`** — add the two columns to `_COLUMN_MIGRATIONS`.
- **`db/crosspost.py`** — rework `get_pending` (new pending rule, select both
  status cols); add `mark_platform(cq_id, platform, status)`; `skip` marks both.
- **`app.py`**:
  - instantiate `bluesky = BlueskyManager()`.
  - `admin_crosspost_dispatch` — drop `action`; for each *connected* platform not
    already `posted`, attempt and record result; unconnected → `skipped`; flash a
    per-platform summary (e.g. "Tumblr ✓, Bluesky ✗: <err>").
  - keep `_build_crosspost` for the Tumblr body/tags; add `_build_bluesky_post`
    for text + card fields.
  - `admin_crosspost_queue` passes `bluesky_connected` + per-item statuses.
- **`requirements.txt`** — add `atproto`.

---

## Complexity justification

Two typed status columns (not a child table): the minimum that makes partial
failure safe and retryable for exactly two platforms; clear to read in the admin
UI and easy for Clover to reason about. A child table is justified only at
platform #3.

---

## Out of scope

- Image cards / Playwright (deferred — separate VPS-root coordination).
- Mastodon (Phase 2, later — its arrival triggers the child-table refactor).
- The counting feature's Tumblr flow (explicitly untouched).
- Auto-posting / trust-threshold auto-dispatch — manual admin queue stays.

---

## Testing holds (live on poet.horse — preview pane can't run any of this)

1. **VPS prep:** `pip install atproto`; set `BLUESKY_HANDLE` +
   `BLUESKY_APP_PASSWORD` in the gunicorn service env; restart.
2. **Tumblr baseline (closes the 1.20 gap):** publish a test poem → it appears
   in `/admin/crosspost-queue` → Crosspost → confirm it lands on Tumblr live.
3. **Bluesky:** same poem/another → confirm the post appears on the `poethorse`
   account with a working link card resolving to the permalink.
4. **Partial-failure retry:** simulate one platform failing (e.g. bad token) →
   confirm the item stays pending with `✗`, and re-Crosspost reposts only the
   failed platform (no double-post on the one that succeeded).
5. **Skip:** confirm Skip resolves an item out of the queue.

---

## Open items — all confirmed (2026-06-16)

- Handle: `poethorse.bsky.social`. ✓
- Post text: `"{title}" a poem of {count} horses by {author}`. ✓
- Card description: short horse-name preview from the poem's first line (revisit
  live if it reads oddly).
