# Phase 2.7 — Image-card export

**Model:** Opus · **Effort:** high *(new render subsystem + new template surface + two connector rewires; the card design itself needs live iteration with Clover)*
**Depends on:** Playwright + Chromium on the VPS — ✅ **verified working 2026-06-18**; Phase 2.2 (crosspost queue), Phase 2.3 (crosspost composition)
**Status:** 🟡 DRAFT — specced 2026-08-11, amended same day (Tumblr images dropped, download cards added), not yet built
**Ships:** every published poem gets a rendered card, generated once at publish and stored as static files; **Bluesky** crossposts carry the image instead of a text sample; poems gain a **download** link to a print-quality PNG; the card doubles as the site's first `og:image`. Backfill covers the existing published corpus.

**Scope amendment (2026-08-11, Clover):** Tumblr photo posts are **out** — Tumblr keeps its
existing 2.2/2.3 **text** crosspost path, completely untouched. The user-facing **download
card is in**, which the original draft had scoped out; that objection was conditional on
per-request rendering and is void now that cards are pre-rendered static files.

Origin: backlog item promoted to early Phase 2 on 2026-05-25 ("image posts outperform
plain-text posts on every platform, sidestep character limits, and avoid link-suppression
penalties"). Technique resolved 2026-06-16 (server-side Playwright, chosen as the
two-for-one with the PQ lazy-cache scrape). VPS prerequisite cleared 2026-06-18. Design
decisions below settled with Clover 2026-08-11.

---

## The load-bearing decision: the image carries the poem, the text does not

**Clover's call (2026-08-11).** Bluesky's `AppBskyFeedPost.Record` has a *single* `embed`
field, and it is a union — `images` | `external` | `record` | `recordWithMedia`. There is
no variant that pairs an external link card with images. So attaching an image means
giving up the 2.3 link card, which was carrying the permalink **outside** the 300-char
text budget.

Rather than fight for budget, the post text stops overlapping with the poem entirely:

| | Phase 2.3 (today) | Phase 2.7 (this spec) |
|---|---|---|
| Poem | sampled into the text, truncated to fit 290 chars | **rendered in the image, complete** |
| Permalink | external link card (free, no text cost) | **plain text in the body** (~24 chars) |
| Text body | header + poem sample + hashtags | header + permalink + hashtags (~100 chars) |
| Embed | `AppBskyEmbedExternal` | `AppBskyEmbedImages` |

This is a simplification, not a cost. `_compose_body` and its whole whole-horse truncation
apparatus (`bluesky.py:31`) leaves the critical path — it stays in the tree as the
**fallback** (see *Failure handling*), unchanged.

### Consequence: alt text becomes mandatory, not decorative

With the poem living only in pixels, the image's alt text is the sole text-accessible copy
of the work. This is an accessibility requirement now. Phase 2.3 explicitly deferred alt
text to "when image cards return" — this is that moment.

- **Alt text = title + author + the complete poem**, one horse-name per token, lines
  preserved with `\n`.
- Bluesky's alt-text ceiling is **~2000 chars — VERIFY against the installed atproto
  version as build step 1** (see *Verification gates*). Nearly every poem clears it easily.
- **Overflow policy:** if the poem exceeds the ceiling, truncate at a *line* boundary,
  append `[…]`, and append `Full poem: https://poet.horse/p/<short>`.

---

## Card format

**Variable height, capped** (Clover's call). Short poems stay punchy, horses stay legible
at one consistent chip size, and only genuinely long poems get cut.

```
CARD_WIDTH        = 1000    # CSS px; ×2 device scale → 2000px output
CARD_MIN_HEIGHT   =  600
CARD_MAX_HEIGHT   = 1400    # ← TUNE HERE (Clover, live)
JPEG_QUALITY      =   85    # ← TUNE HERE; medium-high per Clover
CARD_ART_VERSION  =    1    # bump when horse art changes; drives bulk regen
```

- Card grows with the poem to `CARD_MAX_HEIGHT`, then the poem block clips and a `[…]`
  marker plus the permalink render in the footer as "read the rest".
- **Truncation must be detected, not guessed.** CSS can clip but cannot report that it
  clipped. After load, one `page.evaluate` compares the poem block's `scrollHeight` against
  its `clientHeight` and toggles an `.is-truncated` class; then screenshot. The marker is
  therefore always accurate.
- **View mode: Fancy.** The SVG horses are the entire reason an image outperforms text.
  The card body renders under `body.view-fancy` with animation inert (static render — no
  JS-driven shimmer sweep; the static gold glow stays).
### Three artifacts, one page load

The Bluesky image and the poet-facing download want different things: Bluesky needs to fit
a ~1MB blob, a download of *your own poem* should not look compressed. Both come off the
same render — extra screenshots cost ~200ms each, and crucially **no extra Chromium
launch**, which is the only expensive part.

| File | Format | For | Notes |
|---|---|---|---|
| `<short>.jpg` | JPEG q85, 2× | Bluesky embed | must clear the ~1MB blob ceiling |
| `<short>.png` | PNG, 2× | download link | lossless; prints and archives cleanly |
| `<short>-og.jpg` | JPEG, 1200×630 | `og:image` | clipped from the top of the same page |

A full-colour PNG of a Fancy poem will exceed Bluesky's blob limit, which is why the embed
gets JPEG — but that constraint has no business degrading the copy a poet keeps. Playwright
emits both directly (`type='jpeg', quality=` / `type='png'`), so **no Pillow dependency**.

*(The PNG is droppable if the disk cost bothers — serve the JPEG for download instead. At
~150 poems the PNG set is on the order of tens of MB.)*

### What goes on the card

Title · author · the poem · a footer line carrying `poet.horse/p/<short>`.

The visible permalink on the card is deliberate: images get screenshotted and reposted
away from their original post, and once the Bluesky link card is gone the image is the
only thing that travels. *(Design detail — Clover may veto the footer line without
affecting anything else in this spec.)*

---

## Architecture

### Chips are shared; chrome is not

The card template **reuses `render_poem` / `render_chip` from `macros.html`** — the same
renderer `poem.html`, `poem_queue.html`, `user_profile.html` and `my_pasture.html` already
share (Phase 1.29). It does **not** inherit nav, footer, tag sections, the admin tag
editor, or popover JS, none of which belong in a card.

One renderer, second layout frame. This is what keeps the card from drifting away from the
site as the horse art evolves, and it is why Phase 2.5 (pose variation / walk-cycle /
wander) can land later without a card rewrite.

New files:
- `templates/poem_card.html` — the card frame. Extends nothing; standalone document.
- `static/card.css` — card-specific layout. Imports/duplicates nothing from `style.css`
  that the chips need; `style.css` is loaded first and `card.css` layers the frame on top.
- `image_card.py` — the render module.

The per-chip enrichment the permalink route already does (coat / rev / is_famous, see
`app.py:2262` `poem_permalink`) must be **factored into a shared helper** so the card and
the permalink cannot diverge. This is the one refactor of existing code in the phase.

### The render path never touches the network — including our own server

> **This is the architectural point of the phase. Get it wrong and the site deadlocks.**

The obvious implementation is `page.goto('https://poet.horse/p/<code>')`. **Do not.**
Gunicorn runs **2 sync workers** (`DEPLOYMENT.md`). An admin request that blocks in
Playwright holds worker A while the headless browser's page load needs worker B. One
render survives; two concurrent renders — or one render plus any other slow request —
deadlocks the site.

Instead, the HTML is rendered **in-process** and served to the browser by request
interception:

1. Flask, inside the request context: `html = render_template('poem_card.html', …)`.
2. `page.route('**/*', handler)` where the handler:
   - fulfils `/` with `html`,
   - fulfils `/static/**` from local disk (`send_file`-equivalent, correct content-type),
   - **aborts everything else.** Nothing on the card may fetch from the internet. This is
     a hard guarantee, not a nicety — it means the card render cannot hang on a third-party
     host and cannot leak a request.
3. `page.goto('http://poet.horse.card/')` — a fake origin that exists only inside the
   interceptor, so absolute `/static/...` paths in the shared macros resolve correctly
   without a `<base>` hack.

Benefits beyond the deadlock fix: works on unpublished poems (no visibility gate to
satisfy), works in local dev with no server running, and needs no auth token.

### Browser lifecycle: launch per render, no persistent instance

> **Clover raised reusing one Playwright across requests in short succession. The
> resource intuition inverts here.**

A persistent browser is ~200MB resident **permanently**, and with 2 gunicorn worker
processes that is ~400MB idle whether or not anyone publishes. Launch-per-render costs
~1–2s of startup and **zero** idle. At one or two poems a day, idle cost is the only cost
that matters on that box.

- `chromium.launch()` per render, `browser.close()` in a `finally`.
- Page timeout 20s; the whole render wrapped in a hard timeout.
- **Cross-process lock.** A `threading.Lock` is insufficient — gunicorn workers are
  separate *processes*. Use `fcntl.flock` on `data/.card-render.lock` so two publishes
  landing together serialise instead of racing two Chromiums onto the box.

---

## Lifecycle

### Rendered at publish, not at creation

Creation-time rendering would burn Chromium launches on submissions that are never
approved and on poems still being edited. There are three transitions to `published`:

| Site | Path | Render card? |
|---|---|---|
| `app.py:1759` | trusted/admin direct publish (`bypass_queue`) | ✅ yes |
| `app.py:2606` | admin approve from the poem queue | ✅ yes |
| `app.py:2996` | admin unhide | only if the file is missing |

The first two already call `enqueue_crosspost(poem['id'])` — the card render goes directly
alongside it. Unhide needs no render because the card already exists.

### Storage and serving

- Path: `data/cards/<short_code>.jpg` (+ `<short_code>-og.jpg`, see below).
- `data/cards/` added to `.gitignore` and created at boot next to the existing `init_db()`
  call. Cards are **regenerable, not precious** — losing the directory costs one bulk regen.
- Served by a Flask route `/p/<short_code>/card.jpg` via `send_from_directory`, which
  **404s unpublished poems** (public-only, per Clover). A route rather than an Apache alias
  so that gate is enforceable.

### Regeneration and backfill — build this on day one

Two needs, one mechanism (Clover, 2026-08-11):

1. **Backfill.** Rendering happens at publish, so every poem published before 2.7 ships has
   no card at all. This is not a future nicety — it is required for the feature to work on
   launch day.
2. **Regeneration.** When Phase 2.5 changes the horse art, existing cards are frozen at the
   old look. Without a rebuild path, every art change strands the back catalogue.

- `poems.card_version INTEGER` column, written at render time from `CARD_ART_VERSION`.
  Migration follows the existing `PRAGMA table_info` guard pattern in `db/seed.py`.
- **Both cases are one query.** Backfilled poems have `card_version IS NULL`; stale poems
  have `card_version < CARD_ART_VERSION`. The selector is
  `WHERE status='published' AND (card_version IS NULL OR card_version < CARD_ART_VERSION)`.
- `POST /admin/poem/<short_code>/rebuild-card` — single rebuild, admin-only.

> **A bulk run cannot live in a request.** The original draft said "minutes, fine" — that
> was wrong. The site launched 2026-05-25 at roughly a poem or two a day, so the published
> corpus is on the order of **~150 poems**. At ~2–3s each (Chromium launch dominates,
> serialised under the file lock) a full backfill is **5–8 minutes** in one HTTP request,
> which Apache and gunicorn will time out long before it finishes.

Split by job size:

- **`python -m tools.backfill_cards`** — CLI, run on the VPS. The one-time backfill and any
  full post-art-change regen. No request timeout, resumable (it re-queries the selector
  each pass, so an interrupted run just continues), `--limit` and `--dry-run` flags.
  This is the primary bulk path.
- **`POST /admin/cards/rebuild-stale`** — admin button, processes a **bounded batch**
  (default 10) per click and redirects back with a "N remaining" flash. Convenient for
  small drifts; will not hang the site. Never automatic, never on a public request path.

---

## Connector wiring

### Bluesky (`bluesky.py`)

- `post_poem` gains `image_path` and `image_alt`. When `image_path` is present:
  - `blob = client.upload_blob(data)`
  - `embed = models.AppBskyEmbedImages.Main(images=[Image(image=blob.blob, alt=image_alt,
    aspect_ratio=AspectRatio(width=w, height=h))])`
  - **`aspect_ratio` is required, not optional.** Cards vary in height by design; without
    it, Bluesky guesses and crops tall cards badly in-feed. Dimensions come from the
    screenshot, not from a re-read of the file.
- New `_compose_info_body(header, permalink, tag_render)` — header + permalink + hashtags.
  No poem, no truncation, no budget arithmetic. The 300-char limit stops being a design
  constraint.
- `self_label` (2.3's `sexual` mapping) and `langs=['en']` carry over unchanged.

### Tumblr — unchanged, deliberately

**Out of 2.7** (Clover, 2026-08-11). Tumblr continues to crosspost via the existing
2.2/2.3 **text** path with the external permalink — `queue_handler.py`, `auth.py` and
`_build_crosspost` are not touched by this phase.

This removes the phase's largest unknown. `make_request` (`auth.py:130`) posts JSON only,
and whether legacy `/post` `type='photo'` accepts `data64` that way was untested; the
contingency was a bespoke multipart upload function. All of that is now deferred rather
than risked. Tumblr image posts remain a clean follow-up once the render subsystem is
proven in production — the card files will already exist.

### Download card (poem permalink)

`GET /p/<short_code>/download` → `send_file` of `data/cards/<short>.png` with
`as_attachment=True` and a filename derived from the poem title/short code.

- **Public**, for any published poem — the poems are already public and the permalink
  already renders them; a download is not a new disclosure. 404s unpublished, same gate as
  the card route.
- **This is a static file send. No Chromium, no render, no lock.** The draft scoped this
  out over a resource-exhaustion concern; that concern was entirely about per-request
  rendering and does not survive the pre-render decision.
- Permalink UI: a modest link/button near the existing footer. Placement and label are
  Clover's call at build time.

### `og:image` — free, with one wrinkle

The card is a static file that exists before the poem goes public, so there is no
crawler-triggered render path and no DoS surface. The site has **no `og:image` at all**
today (`templates/poem.html:9`).

The wrinkle: variable-height cards are right for the in-post image but wrong for OG, where
crawlers expect roughly 1.91:1 and will letterbox or badly crop a tall card. Resolution is
a **fixed-ratio OG variant cropped from the top of the same render** — one extra
`page.screenshot` with a `clip` rect, no second page load.

- `data/cards/<short_code>-og.jpg`, 1200×630.
- `poem.html` emits `og:image` + `og:image:width` + `og:image:height` **only if the file
  exists**, and `twitter:card` flips from `summary` to `summary_large_image`.
- **Droppable.** If the OG variant fights the card design, cut it to a follow-up; nothing
  else in this spec depends on it.

---

## Failure handling

Card rendering must never take down a publish or a crosspost.

1. **Render fails at publish** → catch, log, flash a warning to the admin. **The poem still
   publishes.** A missing card is a degraded post, not a lost poem.
2. **Crosspost with no card on disk** → fall back to the **existing Phase 2.3 path**,
   unchanged: text sample + external link card. This is why `_compose_body` stays in the
   tree. Without this fallback, an info-only body with no image would ship a poem-less
   blurb to Bluesky.
3. **Blob upload rejected (size)** → surface the error in the existing per-platform status
   column so Retry Crosspost works; do not silently post without the image.
4. **No card on disk when the permalink renders** → the download link and `og:image` are
   simply **absent**, never present-and-broken. Both are emitted conditionally on the file
   existing. This is also the correct behaviour for the window between deploying 2.7 and
   finishing the backfill.
5. **Backfill interrupted** → harmless. The selector re-queries each pass, so a re-run
   picks up exactly what's still missing. No resume state to corrupt.

---

## Scope

**In:** card render subsystem; `poem_card.html` + `card.css`; render-at-publish for the
three transitions; static storage + serving routes; **download link on the permalink**;
single rebuild + bounded-batch admin regen + **`tools.backfill_cards` CLI**; Bluesky image
embed with alt text and aspect ratio; `og:image` variant; shared chip-enrichment helper;
`playwright` added to `requirements.txt`.

**Out:**
- **Tumblr photo posts** — Tumblr stays on the existing text path, untouched (Clover,
  2026-08-11). Clean follow-up once the render subsystem is proven; the card files will
  already be there.
- Reader / Plain card variants — Fancy only.
- Animated or GIF cards (downstream of Phase 2.5 at the earliest).
- Per-horse or per-collection cards.
- *Automatic* back-catalogue generation. Backfill and regen are **in** scope, but always
  operator-initiated — a CLI run or an admin button click, never a cron, never triggered by
  a page view.
- The PQ lazy-cache scrape. Same Playwright dep, entirely separate build.

---

## Verification gates

Ordered. Each is a real unknown, not a checkbox.

1. **atproto alt-text ceiling and `AspectRatio` model shape** — confirm against the
   installed version *before* writing the embed code. The 2.3 build already hit one of
   these (`send_post` had no `labels` param); assume nothing.
2. **Bluesky blob size in practice** — render the longest realistic poem at
   `CARD_MAX_HEIGHT` and confirm the JPEG lands under 1MB at quality 85. If not, quality
   is the knob, then width.
3. **Chromium under gunicorn, not just under a shell.** The 2026-06-18 smoke test launched
   from an interactive session. Launching from inside a systemd user service with its own
   environment is a different test and must be run before this is called done.
4. **Backfill timing on the real corpus.** Run `tools.backfill_cards --dry-run` first to
   get the actual count, then time one render on the VPS. If the per-card cost is far off
   the ~2–3s estimate, the batch size on the admin button needs revisiting.

*(The Tumblr `data64` gate is gone with the Tumblr scope cut — it was the riskiest of the
original four.)*

---

## Testing (rule 14 — live site, not the preview pane)

The preview pane cannot run Playwright, SQLite, or the publish flow. Everything here is
verified on poet.horse after deploy.

- Publish a short poem → card renders, looks right, permalink footer correct.
- Publish a long poem → truncation marker appears and is *accurate* (not clipped without
  the marker, not marked without clipping).
- Publish a poem with a CW tag → Bluesky self-label still fires (2.3 regression check).
- Crosspost to Bluesky → image appears, alt text carries the full poem, tall card is not
  cropped in-feed, permalink is tappable.
- Crosspost to Tumblr → **still a text post, unchanged** (2.2/2.3 regression check — the
  Tumblr path must be provably untouched by this phase).
- Download link → PNG downloads, opens clean, prints legibly.
- Force a render failure → poem still publishes; crosspost falls back to text + link card;
  download link is absent rather than broken.
- Two publishes in quick succession → serialise, no deadlock, both cards render.
- Paste a permalink into a Bluesky/Discord compose box → OG card preview.
- **Backfill** — `tools.backfill_cards` on the VPS covers the whole published corpus;
  spot-check old poems for cards and working download links.
- Rebuild-stale button → processes its batch, reports remaining, doesn't hang.

---

## Notes for the build

- Deploy runs `uv pip install`, not `sync`, so the existing venv Playwright/Chromium
  install persists. Add `playwright` to `requirements.txt` anyway so a rebuild is
  reproducible.
- `playwright install-deps chromium` **always** fails on this Ubuntu 24.04 box (t64 rename
  of `libasound2`). Ignore its exit code — the launch test is the gate. See
  `DEPLOYMENT.md`.
- Live tuning per the agreed coordination (2026-06-19): `CARD_MAX_HEIGHT`, `JPEG_QUALITY`
  and the card's type/spacing sit behind named constants and CSS vars marked `TUNE HERE`.
  Clover finds values in devtools without committing and hands over the numbers to bake in.
