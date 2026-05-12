# poet.horse — Roadmap & Design Doc

> **Status:** drafted 2026-05-11, updated 2026-05-13. Living doc — every decision here was confirmed
> by the project owner. Items marked **[OPEN]** still need a call before that
> task starts. Each task is independently executable; the suggested Claude
> model + reasoning effort is a hint, not a hard requirement.

## You are here — 2026-05-13

**Done this session:**
- Phase 0.2 ✅ — SQLite schema, `poem_db.py`, `poem_submissions.py`, admin poem queue, `/p/<short_code>` stub, tags seeded
- Phase 0.3 ✅ — `short_code` on every poem, `/p/<short_code>` route live, stub permalink template
- VPS deployment ✅ — gunicorn running on `127.0.0.1:8765` under a systemd user service on zap.rupture.net. Apache vhost request sent to Jon (rupture.net admin); DNS A record for `poet.horse` → `162.221.25.21` already set in Cloudflare.
- Horse dictionary ✅ — `data/horses.json.gz` (~29 MB, properly compressed) committed and pushed; loads 2.1M horses on boot.
- Phase 0.4 ✅ — Clerk integration wired up:
  - `clerk_auth.py`: JWKS-cached RS256 JWT verification (PyJWT + Clerk's `/v1/jwks`)
  - `db/users.py`: user lookups + slug validation helpers
  - `requirements.txt` created (`Flask`, `gunicorn`, `requests`, `PyJWT`, `cryptography`)
  - New routes: `GET /sign-in`, `GET /sign-out`, `POST /auth/clerk/verify`, `GET|POST /setup-account`, `GET /u/<slug>`
  - First-login flow: Clerk JS → POST token → verify → slug picker → user row created
  - Admin is now role-based (`users.role = 'admin'`); PIN login at `/login` remains as fallback
  - `base.html` embeds Clerk JS CDN and shows sign-in/sign-out/user links in nav

**Waiting on:**
- Jon to create the Apache vhost for `poet.horse` → `127.0.0.1:8765`
- Owner: set up `.env` on the VPS and wire it into the systemd service (see below)
- Owner: after first Clerk login, run `UPDATE users SET role='admin' WHERE slug='your-slug';` in the SQLite DB to grant admin access

**VPS environment setup** (one-time, not yet done):
- Service file: `/home/metaphorever/.config/systemd/user/poet-horse.service`
- App directory: `/data/home/metaphorever/horse-counter`
- Venv: `/home/metaphorever/.venv`
- No `EnvironmentFile=` in the service yet — env vars are not set. Steps:
  1. `nano /data/home/metaphorever/horse-counter/.env` — add `SECRET_KEY`, `APP_PINS`, `TUMBLR_CONSUMER_KEY`, `TUMBLR_CONSUMER_SECRET`, `TUMBLR_BLOG_NAME`, `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`
  2. `systemctl --user edit poet-horse.service` — add `EnvironmentFile=/data/home/metaphorever/horse-counter/.env` under `[Service]`
  3. `systemctl --user daemon-reload && systemctl --user restart poet-horse.service`
  4. Install deps — the VPS uses `uv`, not pip:
     ```bash
     source $HOME/.local/bin/env && source ~/.venv/bin/activate
     uv pip install -r /data/home/metaphorever/horse-counter/requirements.txt
     ```

**Next session start:** Phase 0.5 — localStorage → account sync `[sonnet · medium]`
- Or parallel quick wins: `tools/migrate_json_to_sqlite.py` `[sonnet · medium]` and Phase 0.6 ToS routes `[haiku · low]`

---

## 1. What we're building

**poet.horse** is a constrained found-poetry tool. Every word in a poem must be a real horse name from a curated dictionary (~2.1M names). The site is the canonical home for poems. Tumblr (and later Bluesky/Mastodon/etc.) are *outbound* publishing connectors — the website never depends on them.

The current code (a Flask app on PythonAnywhere posting to `counting-horses` on Tumblr) is the kernel. We are migrating it to a real domain on a real VPS, swapping JSON-file storage for SQLite, adding real auth via Clerk, and reframing the UX around *poems on the website*. The Tumblr counter feature comes along for the ride at `/count`.

---

## 2. Settled architecture

| Decision | Choice |
|---|---|
| Domain | `poet.horse` (only one for now; `counting.horse` etc. deferred) |
| Hosting | Existing radio-station VPS (Phase 1). Independent VPS only if traffic / monetization justifies it |
| Deploy | GitHub → VPS via GitHub Actions on merge to `main` |
| Backend | Flask + Jinja + vanilla JS (no SPA) |
| Datastore (poems, users, tags, submissions) | **SQLite** (single file, FTS5 for poem search) |
| Datastore (horse dictionary) | **Static `data/horses.json.gz`** loaded at app start (~30 MB). Not in SQLite |
| Auth | **Clerk** (Google, Apple, GitHub, Facebook, magic link, passkeys). No passwords stored on our side |
| Anonymous flow | Full tool access pre-login. localStorage for stable + drafts + prefs. Anonymous poems are **permanently anonymous** |
| Poem ID | UUID4 (32-hex) internal; **base62 short code** (≈11 chars) for public URL `poet.horse/p/<short>` |
| Tag taxonomy | Multiple curated **categories**, each seeded with common tags + admin-approved user suggestions. MVP categories: **Poem Type** (free verse, haiku, etc.), **Theme** (love, loss, nature, etc.), **Content Warnings** (sex, drugs and alcohol, violence, etc.). New categories addable by admin |
| Tumblr | Retained. Site is canonical; Tumblr is one of N outbound connectors |
| API | Internal-only at launch. Designed for eventual public exposure |
| Editor UI | Always utilitarian + accessible (no horse-body decoration). Famous-horse shimmer kept. Big touch targets. Less drag-dependent (Phase 2 rethink) |
| Display UI (poem viewer) | Two render paths: **plain** (default for accessibility / reduced-motion / explicit pref) and **pasture** (full grass/horse decoration, default for permalinks) |
| Print | Two `@media print` stylesheets: plain text (also = `.txt` download + image-card source for plain) and Victorian broadsheet (also = image-card source for fancy) |

### Famous horses model
Two independent sources, both surfacing the same UI badge with a "why famous" caption on the more-info menu:

1. **IRL famous** — curated JSON: `data/famous_horses.json`. Caption examples: "Kentucky Derby winner", "Triple Crown winner", "Belmont winner", "Breeders' Cup Classic winner".
2. **Site-famous** — derived from real usage on poet.horse. Composite score from (a) appearances in published poems and (b) saves to user pastures (Phase 2+). Top-N gets the badge. Caption: "#3 most-used horse on poet.horse".

A horse can be both. The badge merges both captions. **No voting** — the site never asks users to upvote. Rankings come from curated real-world facts or from real usage signals only.

---

## 3. Deferred / open

These exist as plans but won't be touched until the trigger condition fires. Listed here so they aren't forgotten.

- **counting.horse domain & redirect** — no decision needed for MVP; the existing horse-counter feature lives at `poet.horse/count`. Revisit if/when the domain is purchased.
- **Three-concept model (Stable / Your Pasture / Pasture mode)** — full rollout is **Phase 2**, after Clerk + user identities exist. Phase 1 keeps the current single "Stable" concept (per-user via localStorage; per-account once auth lands).
- **Per-horse on-demand scrape** of pedigreequery (with Cloudflare-aware Playwright session, polite rate-limit, dead-link blacklist) — **Phase 2+**. Notes already in `TODO.md` and braindump.
- **Real coat colors** — needs scraped data; defer until per-horse scrape is live. Hash-based pseudo-colors stay for now.
- **Public API exposure + OpenAPI spec** — internal-first design, public exposure in Phase 3.
- **Theme/mood tag set** (love, loss, humor, etc.) — deferred. Form taxonomy + `explicit/mature` ship at MVP.
- **Editor UX rethink** (less drag-dependent) — Phase 2; needs a focused design conversation. Phase 1 ships chip-stripped + big-target version.
- **Old poem import** from `data/poems/*.json` and the counting-horses Tumblr blog — best-effort one-shot script in Phase 1. Fresh start is acceptable if conversion is messy.
- **Lawyer review of ToS** — before monetization, not before launch. Plain-English placeholder ships in Phase 0.
- **Ambient field horses + emoji-sprinkle background** — Phase 2, owner-prioritized.
- **Multi-format line breaks** in poem schema — MVP encodes only `newline` breaks, with a publish-time warning when a poem has empty lines (intentional vs. strip).

### Items I made a default call on — flag if wrong

- **Internal poem ID:** UUID4 hex; **public short code:** 11-char base62 generated by `secrets.token_urlsafe(8)` then sanitized. Collision check on insert.
- **Counting feature in MVP:** stays at `poet.horse/count` with no redesign. Tumblr posting from there continues to work for admins.
- **Dictionary stays as a static file**, not migrated to SQLite. Lookups are O(1) via `word_index`; SQLite would only add overhead.
- **Clerk plan:** start on the free tier (≤10k MAU). Re-evaluate if we hit the limit.

---

## 4. Model + reasoning-effort guidance

Throughout the phases below, every task has a tag like `[sonnet · medium]`. Translation:

| Tag | When to use it |
|---|---|
| `[haiku · low]` | Mechanical edits, renames, boilerplate, single-file additions with obvious shape |
| `[sonnet · low]` | Small, well-defined feature work; one or two files; no architectural calls |
| `[sonnet · medium]` | Most feature work — touches a few files, requires reading surrounding code |
| `[sonnet · high]` | Anything where design quality matters: UX, schema, multi-component refactors, animation/perspective, error-prone integrations |
| `[opus · high]` | Novel architecture, research-heavy work, things where getting the abstraction right matters more than speed |

Models named: `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-7`.

---

## Phase 0 — Foundations (pre-launch infra)

Goal: clean cutover-ready infra. App still works the way it does today, but the deployment story, data layer, and auth are the new ones.

### 0.1 VPS provisioning and deploy pipeline `[sonnet · medium]`

- Owner action: register `poet.horse` and point DNS A record to the VPS.
- Set up Apache reverse proxy → gunicorn → flask. systemd unit for the gunicorn service.
- Provision Python 3.11+, Let's Encrypt cert via certbot.
- GitHub Actions workflow `.github/workflows/deploy.yml`: on push to `main`, ssh to VPS, `git pull`, install deps, restart service. Use repo secrets for SSH key.
- Acceptance: pushing to `main` deploys; `https://poet.horse/` serves the current app over TLS.

### 0.2 SQLite + migration of JSON state `[sonnet · high]`

- Add `data/poet.db` (gitignored). Use Python stdlib `sqlite3` — no ORM unless it earns its place.
- Schema (initial):
  - `users` (id, clerk_id UNIQUE, slug UNIQUE, display_name, joined_at, role)
  - `poems` (id INTEGER PK, short_code UNIQUE, title, lines_json, status, author_user_id NULL, author_display_name, created_at, published_at, edited_at)
  - `poem_tags` (poem_id, tag_id, applied_by user_id, status: pending/approved)
  - `tag_categories` (id, slug UNIQUE, label, sort_order, behavior: enum `single_select`/`multi_select`/`content_warning`, created_at)
  - `tags` (id, slug UNIQUE, label, category_id → tag_categories, status: active/pending/rejected, suggested_by user_id NULL, created_at)
  - `reports` (id, target_type: poem/display_name/slug, target_id, reporter_user_id NULL, reason, created_at, status)
  - `submissions` (id, poem_id, status: pending/approved/rejected, submitted_at) — replaces `submissions.json`
  - `drafts` (id, user_id NULL, lines_json, title, updated_at) — replaces in-memory + `stable.json`
  - `stable_horses` (user_id, name, display, url, remaining) — server-side stable for logged-in users
- Write `tools/migrate_json_to_sqlite.py`: idempotently imports `submissions.json`, `data/poems/*.json`, and `stable.json` into the new schema. Best-effort; logs anything skipped.
- Replace [submissions.py](submissions.py), [poem_store.py](poem_store.py), and the `stable_*` paths in [poetry.py](poetry.py) with sqlite-backed equivalents. Keep function signatures so [app.py](app.py) doesn't shift.
- Acceptance: app boots against SQLite; `migrate_json_to_sqlite.py` run twice produces no duplicates; existing flows still work.

### 0.3 Public short-code + permalink URL system `[sonnet · medium]`

- `tools/shortcode.py`: `generate_short_code()` returns `secrets.token_urlsafe(8)`, length-checked, URL-safe (strip `_-`).
- New route: `GET /p/<short_code>` (200 stub for now — full renderer is Phase 1).
- Update [poem_store.py](poem_store.py) (now sqlite) to populate `short_code` on insert with collision retry.
- Acceptance: every saved poem has a unique 11-ish-char short code reachable at `/p/<code>`.

### 0.4 Clerk integration `[sonnet · high]`

- Add Clerk Flask SDK. Configure: Google, Apple, GitHub, Facebook, magic-link email, passkeys.
- New routes: `/sign-in`, `/sign-out`, `/u/<slug>` (basic).
- On first login, create row in `users` with `clerk_id`. Prompt for unique slug (URL-safe, 3-32 chars, [a-z0-9-]). Display name defaults to Clerk profile name; user can edit.
- Replace the PIN admin login (`config.check_pin`) with **role-based admin**: `users.role = 'admin'` set manually in DB for the owner's account. PIN remains as a fallback only if Clerk is unreachable.
- Update `app.py:login_required` decorator to check Clerk session OR PIN-fallback.
- Acceptance: a fresh Google login lands on a "pick your slug" form; second visit goes straight to `/u/<slug>`.

### 0.5 localStorage → account sync on first login `[sonnet · medium]`

- On first login, the client posts current `horse-stable`, `horse-poem-name`, `horse-poem-tumblr`, `horse-page-size` to a new `/me/sync` endpoint.
- Server merges into `stable_horses` and `users.preferences_json`. Client clears the local copies.
- "It already remembered" UX: show a one-time toast.
- Acceptance: build a stable of 3 horses while logged out, log in, see them on the server-side stable.

### 0.6 Plain-English ToS + privacy placeholder `[haiku · low]`

- New routes/templates: `/terms`, `/privacy`. Plain-language summary at top, formal terms below (per spec). Link in footer.
- Owner reviews wording before launch; lawyer review pre-monetization.
- Acceptance: pages render; footer link present site-wide.

---

## Phase 1 — MVP soft launch

Goal: poet.horse is a complete website that lets anyone compose, publish, and read horse poems. Tumblr is one optional outbound connector for the admin.

### 1.1 Editor refresh — chips, big targets, famous shimmer `[sonnet · high]`

- Strip horse-body decoration (legs, coat shapes) from chips inside [templates/poetry.html](templates/poetry.html).
- Keep coat color palette and famous shimmer.
- Increase tap targets (44×44 minimum), increase spacing.
- Keep current drag interactions; add a click-to-add fallback path on every chip ("click to add to current line"). Note this is an interim — full rethink is Phase 2.
- Acceptance: every chip is keyboard-focusable; touch testing on a small phone shows no accidental drags; visual diff against current is dramatically simpler.

### 1.2 Tag taxonomy + selection UI `[sonnet · medium]`

- Seed `tag_categories` and `tags` with curated baselines (owner to edit before launch):
  - **Poem Type** (`single_select`): free verse, haiku, limerick, sonnet, couplet, ballad, ode, prose poem, concrete, found, other
  - **Theme** (`multi_select`): love, loss, nature, humor, hope, longing, anger, joy, memory, place, animals, the body, time, dreams, work, faith, other
  - **Content Warnings** (`content_warning`, multi_select with display-time consequences): sex, drugs and alcohol, violence, self-harm, death, slurs, mature themes
- Editor UI: one section per category. Single-select renders as a radio chip group; multi-select as a toggleable chip cloud; content_warning gets warning-styled chips with a tooltip explaining display behavior. Each section has a "suggest a new tag" affordance that submits to the pending queue scoped to that category.
- Acceptance: poems can be tagged across all three MVP categories; tagged poems show their tags grouped by category on the permalink.

### 1.3 Admin tag management `[sonnet · medium]`

- Admin route `/admin/tags`: list pending suggestions grouped by category. Approve / reject / merge into existing / move to a different category. Create new categories on the fly.
- In the admin "review submission" flow, suggested tags appear inline next to the poem. Admin can approve a tag (adds to `tags`), reject the tag but keep the poem, move a tag to a different category, or override the tag set entirely.
- Lightweight UI: drag tags between categories, type-to-merge.
- Acceptance: a user-suggested tag goes from poem submission → admin queue → approved (in chosen category) → available in the editor's picker for the next user.

### 1.4 Poem permalink + Open Graph `[sonnet · medium]`

- `/p/<short_code>` renders the poem with: title, attribution, tags, published date, two view modes (plain / pasture — see 1.5).
- Open Graph tags: `og:title`, `og:description` (first line of poem + count), `og:url`, `og:type=article`, `og:image` (defer to Phase 2 image card; meanwhile use a static OG card).
- Acceptance: pasting a poem URL in Slack/Discord/iMessage shows a rich preview with the poem title and author.

### 1.5 Two-mode poem renderer (plain / pasture) `[sonnet · high]`

- Plain mode: utilitarian, semantic HTML, no animation, screen-reader friendly. Used as the default when the user has reduced-motion or has toggled reader mode.
- Pasture mode: full grass background + decorated horse chips (current Tumblr-theme styling, ported in). Default for permalink visits.
- Toggle button in the poem header, persisted to localStorage (and to `users.preferences_json` if logged in).
- Acceptance: a permalink loads in pasture by default; toggle persists across sessions.

### 1.6 Public poem feed + chronological browse `[sonnet · medium]`

- `/` (homepage) shows: random curated poem hero (admin can pin), recent poems list below, "make a poem" CTA.
- `/recent` paginated chronological feed (50/page).
- Acceptance: published poems appear on /recent in reverse-chrono order; homepage hero rotates.

### 1.7 Empty-line warning at publish time `[haiku · low]`

- Before submission, if any line in the poem is empty, show a modal: "Empty line detected — keep as a stanza break, or strip?" with two buttons.
- Acceptance: submitting with empty lines triggers the modal; choosing "strip" removes them client-side before POST.

### 1.8 Export: plain text copy, HTML copy, .txt download `[sonnet · low]`

- Buttons on the permalink page: "copy as text", "copy as HTML", "download .txt".
- HTML copy includes minimal inline styling so it survives paste into rich-text contexts.
- Acceptance: each button works in Chrome and Safari.

### 1.9 Plain-text print stylesheet `[sonnet · medium]`

- `@media print` for plain mode: serif font, generous margins, poem centered, attribution caption, `poet.horse` URL in footer.
- "Print" button on permalink invokes `window.print()`.
- Acceptance: print preview on a poem looks like a poem on a page; no UI chrome bleeds through.

### 1.10 Reader-mode toggle (site-wide) `[sonnet · medium]`

- Always-visible toggle in header. Sets a `prefers-plain` localStorage flag (and `users.preferences_json` if logged in).
- When set, every renderer uses the plain path. Respects `prefers-reduced-motion` and `prefers-contrast` automatically.
- Acceptance: toggle on → permalink loads in plain by default; refresh persists choice.

### 1.11 Admin moderation queue (publish-to-site) `[sonnet · high]`

- Rework `/submissions`: queue is poem-first, not Tumblr-post-first. Each row: poem preview (plain), suggested tags, attribution, "publish to site" / "publish + cross-post to Tumblr" / "edit and publish" / "reject".
- Publish flips `poems.status` to `published`, sets `published_at`. Cross-post button reuses the existing Tumblr submit path.
- The original counter-submission queue stays as-is (it's a different flow), routed under `/admin/counter-queue` or similar.
- Acceptance: a public poem submission lands in the admin queue; admin clicks "publish" → poem appears on /recent and at its permalink.

### 1.12 Report button + report queue `[sonnet · medium]`

- "Report" button on every poem permalink and on poet display names. Logged-out users can report (rate-limited by IP).
- Admin route `/admin/reports`: list pending, approve (hide poem / rename slug / delete) or dismiss.
- "One-click hide pending review" admin button on poems.
- Acceptance: report submitted → appears in admin queue → admin actions take effect.

### 1.13 Poet profile `/u/<slug>` `[sonnet · medium]`

- Public page: display name, slug, joined date, poems published (paginated reverse-chrono), small "edit profile" link if owner is viewing their own.
- Owner can edit display name (slug is permanent post-Phase-0 — confirm UX for unique-slug enforcement).
- Acceptance: visiting a slug shows that poet's published poems; anonymous-poem authors have no profile.

### 1.14 RSS feed `[sonnet · low]`

- `/feed.xml` for all published poems (most recent 50). `/feed.xml?tag=haiku` and `/u/<slug>/feed.xml` for filters.
- Acceptance: feed validates at validator.w3.org/feed; opens in a reader.

### 1.15 Rate limiting `[sonnet · low]`

- Add `flask-limiter` (Redis if VPS has it, in-memory otherwise). Limits: poem submission (5/hour anon, 30/hour logged-in), reports (3/hour per IP), search (60/min), API endpoints (per-route).
- Acceptance: exceeding the limit returns 429 with retry-after header.

### 1.16 One-shot import of existing data `[sonnet · medium]`

- `tools/import_legacy.py`: pulls `data/poems/*.json` (the current store) into SQLite as published poems with their existing IDs as `short_code` (collision-checked). Optionally pulls poems posted to the counting-horses Tumblr via the API and imports those too, attributing to "anonymous (legacy)".
- Best-effort; failures logged not raised.
- Owner runs once before DNS cutover.
- Acceptance: post-run, `/recent` shows a populated feed.

### 1.17 DNS cutover + PythonAnywhere shutdown `[haiku · low — owner action]`

- Update DNS to point poet.horse at the VPS.
- Once new site is verified live, shut down the PA app. (Optional: configure PA to redirect to poet.horse — bonus.)

---

## Phase 2 — Beta & feedback (after Tumblr / Metafilter soft launch)

Triggered when soft launch is live and traffic / feedback is flowing. Tasks here can be ordered freely.

### 2.1 Editor UX rethink `[opus · high]`

- Owner has flagged the editor needs a real redesign — less drag-dependent, more thoughtful affordances.
- This task starts with a design conversation, not code. Produce a written design doc (`docs/editor-redesign.md`) covering: input model alternatives (keyboard/click-to-add, sortable list, free-text-with-autocomplete, hybrid), accessibility plan, mobile vs desktop ergonomics. Get owner sign-off before implementation.
- Implementation follows in a sub-task.
- Acceptance: design doc merged; implementation matches the doc.

### 2.2 Explicit/mature opt-in display `[sonnet · medium]`

- Per-user preference (logged-in) and localStorage flag (anonymous): "show explicit/mature poems".
- Poems tagged `explicit/mature` are blurred + click-to-reveal in feeds; permalink loads with a confirm gate.
- Acceptance: anonymous default-hides; toggling reveals; preference persists.

### 2.3 Image card export `[sonnet · high]`

- Render the fancy print view in a hidden div, capture to PNG via `html2canvas` (client) OR a server-side Playwright render (more reliable). Owner picks.
- "Save as image" button on permalink.
- Acceptance: clicking the button downloads a high-DPI PNG of the poem styled per fancy-broadsheet.

### 2.4 Fancy broadsheet print stylesheet `[sonnet · high]`

- Victorian horse-racing broadsheet aesthetic — references in spec PDF (Bell's Life, Tattersalls catalogues, early Derby programs). Ornamental rules, mixed type hierarchy, woodcut borders.
- High contrast, print-safe, no transparency.
- Acceptance: printing in fancy mode produces a broadsheet-looking page; doubles as image-card source.

### 2.5 "Horsified HTML" copy `[sonnet · medium]`

- Copy button: poem HTML + a `<link rel="stylesheet" href="https://poet.horse/embed.css">`. Pasted into a Tumblr/personal site, the poem renders with horse styling.
- Publish `embed.css` as a versioned static file.
- Acceptance: paste output into a Tumblr theme test, horses render styled.

### 2.6 oEmbed support `[sonnet · medium]`

- `/oembed?url=<permalink>` returns oEmbed JSON. Add `<link rel="alternate" type="application/json+oembed">` on permalink pages.
- Acceptance: a poem URL embeds inline on Discord / supported platforms.

### 2.7 Per-horse on-demand scrape (Cloudflare-aware) `[opus · high]`

- See `TODO.md` for the existing notes. Trigger on user clicking "more info" on a horse name not in cache.
- Persistent Playwright session that has cleared the Cloudflare challenge once; cookie reuse for subsequent fetches.
- Polite: 1 req/sec max, randomized delay. Cache result indefinitely. Mark dead links in `data/horse_overrides.json`.
- Acceptance: clicking "more info" on a horse fetches and caches its PQ data within 3s; second click is instant.

### 2.8 Real coat color encoding `[sonnet · medium]` (depends on 2.7)

- Map PQ color codes (`b`, `ch`, `gr/ro`, `blk`, etc.) to CSS variables.
- Use scraped color when present; fall back to hash-based for unknowns.
- Acceptance: Black Beauty renders dark.

### 2.9 Three-concept UI: Stable / Your Pasture / Pasture mode `[sonnet · high]`

- Implement the braindump terminology now that auth is solid:
  - **Stable** — current working area for one poem (existing).
  - **Your Pasture** — per-account collection of saved horses across all poems. New "add to pasture" / "remove from pasture" buttons. New `/me/pasture` page.
  - **Pasture mode** — display convention (the grass-styled poem renderer from 1.5; upgrade with movement toggles per user preference).
- "Pasture search mode" (braindump): toggle on the search page that adds results to a visual pasture instead of a list.
- Acceptance: each concept is distinct in UI and code; no terminology bleed.

### 2.10 Browse pages `[sonnet · medium]`

- `/horse/<name-slug>` — all poems featuring this horse + horse metadata (registry, country, birth year, scraped fields if any).
- `/u/<slug>` — already exists (1.13); add filters.
- `/tag/<tag-slug>` — all poems with this tag.
- Acceptance: each page paginates, sorts (newest / most-reported-positive / random), and is link-shareable.

### 2.11 Search inside poems `[sonnet · high]`

- SQLite FTS5 virtual table on `poems(title, lines_text, author_display_name, horse_names_concat)`.
- `/search?q=...` UI with filters by tag, by poet, by horse-in-poem.
- Acceptance: searching for "rosebud" returns poems containing horses named Rosebud, poems with "rosebud" in the title, and poets named Rosebud.

### 2.12 Random poem button `[haiku · low]`

- Header button + `/random` route that 302s to a random published-poem permalink.
- Acceptance: clicking it lands on a different poem each time.

### 2.13 Famous-on-poet.horse popularity stats `[sonnet · medium]`

- Nightly cron computes a per-horse usage score from real signals: (a) count of distinct published poems containing the horse, (b) count of users with the horse in their Pasture (depends on 2.9). Tunable weights, default equal.
- Top-N gets the "site-famous" badge; cache the rolling list in `data/site_famous.json`.
- Merge with IRL famous list when surfacing the more-info menu (e.g. "Kentucky Derby winner · #3 most-used on poet.horse").
- Acceptance: the more-info menu on a popular horse shows both reasons; rankings shift sensibly as new poems are published.

### 2.14 Ambient field horses + emoji-sprinkle background `[sonnet · high]`

- Per the braindump z-index plan: base color → SVG grass tile → emoji sprinkle (☘🍀🍄‍🟫🍄🌾🪾🌳, faux perspective, varied sizes) → styled horses → UI layer.
- Few horses gently random-walk in the background of pasture views and the homepage hero.
- Respect `prefers-reduced-motion` (no animation when set).
- Acceptance: pasture view has a believable field; reduced-motion users see static.

---

## Phase 3 — Growth (if concept has legs)

Triggered when sustained traffic justifies the lift.

### 3.1 Bluesky bot `[sonnet · high]`

- Daily poem-of-the-day post via AT Protocol. Bluesky audience is the highest-priority target per spec.
- Cron job; uses image card export (2.3) for rich previews.
- Acceptance: scheduled post lands daily on the bot account.

### 3.2 Mastodon bot `[sonnet · medium]`

- Same as 3.1 but for Mastodon.

### 3.3 Public read API + OpenAPI spec `[sonnet · high]`

- Promote internal endpoints: poem by ID, poems by poet, poems by horse, horse-database lookup, random poem, random horse.
- Generate `openapi.yaml`. Serve `/api/docs` (Swagger UI).
- Per-key rate limits via API tokens (admin-issued for now).
- Acceptance: API docs are public; an external curl call returns JSON.

### 3.4 Horse database public download `[haiku · low]`

- `/data/horses.json.gz` static download with a license file. Credit/backlink culture.
- Acceptance: file is downloadable; license clearly states terms.

### 3.5 Hall of fame `[sonnet · medium]`

Two distinct halls, same principle as the famous-horses model: rankings come from curated real-world facts or real site-usage signals — never from voting.

- **Curated hall** at `/hall-of-fame/curated`: admin pins exceptional poems (e.g. featured by Metafilter, included in an anthology, won an off-site contest). Caption explains why.
- **Most-used poems hall** at `/hall-of-fame/popular`: derived from real usage signals — view counts on permalinks, copy/export button presses, and (Phase 2+) inclusion of constituent horses in user pastures. Tunable weights; nightly recompute.
- Acceptance: admin can pin / unpin a poem in the curated hall with a caption; the popular hall updates daily from logged signals.

### 3.6 Independent VPS migration `[sonnet · medium — partly owner action]`

- If radio-station VPS becomes inappropriate or traffic warrants it: provision Hetzner/DigitalOcean (~$6/mo), reuse the existing GitHub Actions deploy (just swap secrets), DNS cutover.
- Acceptance: same site, new IP, no downtime > 5 min.

---

## Phase 4 — Monetization (if revenue threshold met)

Trigger: ~$20/mo sustained tip income, or interest from a small ad partner.

### 4.1 Ko-fi tip jar `[sonnet · low]`

- "Keep the horses fed" embed in footer. Single Ko-fi link. No platform-side handling.
- Acceptance: link clicks register on Ko-fi.

### 4.2 Tasteful static ads `[sonnet · low]`

- Single Carbon Ads (or equivalent) placement. No tracking pixels.
- Hide for ad-free supporters (4.3) and for reader mode.
- Acceptance: ad renders in one consistent slot; absent for opted-out users.

### 4.3 Supporter ad-free key flow `[sonnet · medium]`

- Ko-fi donation triggers code generation (manual at first, Ko-fi webhook later).
- User redeems code at `/redeem`; sets `users.flags.ad_free = true` (and localStorage flag for anon users).
- Acceptance: redemption hides ads for that account.

### 4.4 Supporter cosmetic flair `[sonnet · low]`

- Optional badge ("patron of the arts" + horse emoji) shown next to display name on poems. User toggles in profile settings.
- Acceptance: badge appears when toggled.

### 4.5 Lawyer review `[owner action]`

- Pre-monetization: have the ToS reviewed.

### 4.6 Merch / book anthology exploration `[owner action]`

- Print-on-demand for poems. Anthology of community-curated favorites. License terms already cover this (user grants perpetual royalty-free reproduction license for poems).

---

## 5. Cross-cutting commitments

These apply to every phase; future Claudes should not violate them.

- **Accessibility-first.** Every interactive element keyboard-reachable. Every image alt-tagged. Every animation behind `prefers-reduced-motion`.
- **No tracking.** No analytics SDKs, no third-party pixels, no fingerprinting. Use server logs for traffic. Plausible (self-hosted) is acceptable later if needed.
- **Plain-mode parity.** Every feature must work in plain (reader) mode. If a feature can only exist in pasture mode, that's a flag to redesign it.
- **The dictionary stays a fact, not a vibe.** Don't filter horses by name appropriateness — moderation happens on poems, not on the source data. Per spec.
- **Admin work is rare and explicit.** Don't automate admin actions, don't hide them behind heuristics. Curation is the product.
- **Web 1.0 ethos.** Static where possible, light JS, view-source-able. The audience will notice.
- **No upvotes, no engagement metrics surfaced to users.** Any "popular", "famous", or "hall of fame" ranking comes from curated real-world facts or from real site-usage signals (poem occurrences, pasture saves, view counts, exports). Never from a thumbs-up button.

---

## 6. How to use this doc

When opening a fresh session to do work, point Claude at the relevant section:

> "Implement task 1.5 from ROADMAP.md."

Claude reads the section, applies the suggested model + effort, and returns a PR-shaped change. The acceptance criteria are the contract.

When a task uncovers something this doc didn't anticipate, update this doc in the same PR — don't let drift accumulate.
