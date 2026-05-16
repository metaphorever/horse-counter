# poet.horse — Roadmap & Design Doc

> **Status:** drafted 2026-05-11, last full revision 2026-05-16. Living doc — every decision here was confirmed
> by the project owner. Items marked **[OPEN]** still need a call before the
> task starts. Each task is independently executable; the suggested Claude
> model + reasoning effort is a hint, not a hard requirement.

## You are here — 2026-05-16

**Done (Phase 0 — Foundations):**
- 0.1 VPS provisioning & deploy ✅ — gunicorn under systemd on zap.rupture.net, Apache vhost via Jon, Cloudflare proxied, Let's Encrypt cert auto-renewing. Full notes in `memory/vps_hosting.md`.
- 0.2 SQLite + initial schema ✅ — `data/poet.db` with users, poems, submissions, tags. `poem_db.py`, `poem_submissions.py` wired in.
- 0.3 Short-code permalink ✅ — `/p/<short_code>` route live with a stub renderer.
- 0.4 Clerk integration ✅ — `clerk_auth.py`, JWKS-verified sessions, `/sign-in`, `/sign-out`, `/setup-account`, `/u/<slug>`. Role-based admin; PIN remains as fallback.
- 0.5 localStorage → account sync ✅ — `/me/sync` endpoint, `db/stable.py`, per-user `stable_horses` + `preferences_json` hydration on `/poetry`. Idempotent INSERT OR IGNORE; client clears local copies and fires a one-time toast. Verified in production 2026-05-15.
- 0.6 ToS / Privacy / Data-Deletion pages ✅ — `/terms`, `/privacy`, `/data-deletion`. Plain-English summary box at top of each. Email-based deletion flow. Minimal site-wide footer with legal links. Verified in production 2026-05-15.

- 1.1 Top-level nav + user menu ✅ — full IA in `base.html`: logo, Home, Read Poems (Featured/Browse/Random submenu), Write Poems, Pasture, Count; Sign In / user dropdown (Published, Drafts, My Pasture, Saved Poems, Saved Horses, Edit Profile, Sign Out). Mobile hamburger. `user_required` decorator. Coming-soon stubs for all not-yet-implemented destinations. Verified 2026-05-15.
- 1.2 Editor pain-fix ✅ — horse-body decoration (legs/head/tail/tilts) stripped from editor chips; chips are now real `<button>`s with 44×44 tap targets, focus ring, and `aria-label`. Canonical tap interaction is a context-aware **chip menu** (Add to poem · Send to My Pasture · Remove for stable chips; Move left/right/to last line · Send back to stable · Send to My Pasture · Remove for poem chips). Keyboard nav with Arrow / Enter / Escape; Escape returns focus to the chip. Drag is preserved with a 6 px movement threshold (sub-threshold release becomes a menu open); during drag, an **ephemeral drop-zone bar** appears at the viewport bottom (Drop to last line · Send to My Pasture · Remove) and disappears on release. New `pasture_horses` table + `POST /me/pasture/add` lights up the menu/zone end-to-end for signed-in users; logged-out users get an inline sign-in prompt. The chip-menu component is intended to be re-used by 1.7's horse popover. Coat colors preserved. Drag landing caret (green vertical bar on the chip edge where the dragged horse will land) shipped as part of the same PR. **Note (post-ship):** owner reconsidered the strip-decoration decision — full whimsical chip styling (heads/tails/legs/tilts) should come back as the default, with plain chips as an accessibility opt-in. This will be addressed in a dedicated styling session that prototypes fancy/plain/high-contrast/typography-only print modes side-by-side; the architecture in 1.2 is reskinnable, the current plain look is provisional.
- 1.5 Poem permalink renderer + Open Graph ✅ — `/p/<short_code>` now renders the full poem page: title (Playfair serif), attribution with linked display name + published date, optional **After ___** caption (linked or unlinked depending on whether `inspired_by_url` is set), the poem body with horse-name links, tags **grouped by category** (with content-warning visual treatment for that category), and a footer with horse/word counts + the short code. The plain/pasture **view-mode toggle** is wired (button + `data-view-mode` attribute on the article + localStorage persistence) so Phase 1.6 can plug in pasture-mode CSS without touching this scaffold. Open Graph tags emitted in `<head>`: `og:title`, `og:description` (first non-empty line's horse list + total horse count), `og:url`, `og:type=article`, `og:site_name=poet.horse`, `twitter:card=summary`, plus `article:published_time` when present. Unpublished poems are visible to the author and admins only (soft secret — short codes are long enough that guessing them is impractical, the worst case is a draft URL being shared). Templates renamed `poem_stub.html` → `poem.html` to match the route's purpose. Acceptance: pasting a published poem URL in Slack/Discord/iMessage will show a rich preview with the title and a horse-list description; the static-OG-card upgrade is deferred to the Phase 2.3 image-card export.
- 1.3 Tag taxonomy + selection UI ✅ — four MVP tag categories seeded (`Poem Type` single_select, `Theme` multi_select, `Linguistic Features` multi_select, `Content Warnings` content_warning) with 42 baseline tags including a new `After / Translation` in Poem Type for horse-translations of existing work. Publish modal expanded: optional **After ___** attribution pair (`inspired_by_text` + `inspired_by_url` on `poems`) for crediting source works, plus a per-category section with radio/checkbox chips and a "+ Suggest a new ___ tag" button that submits to a `/tags/suggest` endpoint as `status='pending'` (scoped to the category). Submitter-applied tags land on `poem_tags` with `status='pending'` for 1.13's admin review. Server-side validation drops unknown / non-active tag IDs and dedupes single-select selections. Trust scaffold added: `users.trust_level` column (`pending` default, acted on in 1.13) + empty `data/flagged_horse_names.json`. Idempotent migration + seed runs on every `init_db`. The pending-tag "+ Suggest" UI currently uses a `prompt()` for the input — fine for MVP, may upgrade to inline input later. Verified locally end-to-end: schema migrates clean, tag selection radios/checkboxes behave per category behavior, single-select dedup confirmed both client and server, /tags/suggest handles happy path / duplicate (409) / empty (400), poem insert carries through inspired_by + tag_ids.
- 1.22 Attribution footer + Ko-fi support ✅ — Weatherhead citation as `<figure><blockquote cite="…"><figcaption>` with italic serif typography. Plain text Ko-fi link in the footer (🍀 Support poet.horse on Ko-fi). No floating widget — the plain link is the canonical pattern; clover-emoji touchpoints in Phase 2.13 will reuse the same anchor. Verified 2026-05-15.
- **Nav/footer chrome polish (2026-05-16)** ✅ — nav lifted out of the container and placed above the top fence; footer lifted out and placed below the bottom fence. Both wrapped in full-width tan (`#f0ead8`) bars so they're legible over the grass pattern. Mobile hamburger and dropdowns still work; no structural changes to nav or footer content. Shipped as [PR #10](https://github.com/metaphorever/horse-counter/pull/10).

**Phase 0 is closed. The site has its new shell.**

## Up next — Phase 1 continues

Next natural cluster:

- Soft-launch list is now mostly the page-side work: **1.6** (two-mode renderer — pasture-mode CSS that plugs into the toggle scaffold 1.5 shipped), **1.8** (Featured / Browse / Random), **1.9–1.12** (publish UX polish + reader-mode), **1.13** (admin moderation queue + tag review using the `pending` rows 1.3 wired up).
- Open style-session for chip decoration restoration + plain-chips preference + side-by-side prototype of fancy / plain / high-contrast / typography-only print styling.

**Known open bugs (track separately in `TODO.md`):**
- Tumblr post CSS desync — Tumblr appears to strip `class` attributes; horse tile structural styling is lost on new posts. Likely needs data-attribute selectors or inlined structural CSS. **Deprioritized** — most Tumblr users view in dashboard mode where CSS is stripped anyway. Revisit only after the website CSS is finalized.

---

## 1. What we're building

**poet.horse** is a constrained found-poetry tool. Every word in a poem must be a real horse name from a curated dictionary (~2.1M names). The site is the canonical home for poems. Tumblr (and later Bluesky/Mastodon/Threads/etc.) are *outbound* publishing connectors — the website never depends on them.

The current code (a Flask app originally on PythonAnywhere posting to `counting-horses` on Tumblr) is the kernel. We're now running on a real VPS at poet.horse with SQLite storage and Clerk auth. The remaining work is to **reframe the UX around poems on the website**, with Tumblr and other platforms relegated to optional outbound bots. The horse-counter feature comes along for the ride at `/count`.

---

## 2. Settled architecture

| Decision | Choice |
|---|---|
| Domain | `poet.horse` (only one for now; `counting.horse` etc. deferred) |
| Hosting | Existing radio-station VPS (zap.rupture.net). Independent VPS only if traffic / monetization justifies it |
| Deploy | GitHub → VPS via GitHub Actions on merge to `master` (deploy pipeline pending — currently manual `git pull` + service restart) |
| Backend | Flask + Jinja + vanilla JS (no SPA) |
| Datastore (poems, users, tags, submissions) | **SQLite** (single file, FTS5 for poem search) |
| Datastore (horse dictionary) | **Static `data/horses.json.gz`** loaded at app start (~30 MB). Not in SQLite |
| Auth | **Clerk** (Google live, others pending OAuth provider setup). No passwords stored on our side |
| Anonymous flow | Full tool access pre-login. localStorage for stable + drafts + prefs. Anonymous poems are **permanently anonymous** |
| Poem ID | UUID4 (32-hex) internal; **base62 short code** (≈11 chars) for public URL `poet.horse/p/<short>` |
| Tag taxonomy | Multiple curated **categories**, each seeded with common tags + admin-approved user suggestions. MVP categories: **Poem Type**, **Theme**, **Content Warnings**, **Linguistic Features**. New categories addable by admin |
| Cross-posting | Admin-flagged poems land in a queue; scheduled bots (Tumblr, Bluesky, Mastodon, Threads, X) pull from the queue on their own cadence. Same schedule is fine for MVP; schema supports independent schedules later |
| API | Internal-only at launch. Designed for eventual public exposure |
| Editor UI | Always utilitarian + accessible (no horse-body decoration). Famous-horse shimmer kept. Big touch targets. Phase 1 ships a minimum-viable pain-fix; Phase 2 is a full editor rethink with multiple toggleable styles |
| Display UI (poem viewer) | Two render paths: **plain** (default for accessibility / reduced-motion / explicit pref) and **pasture** (full grass/horse decoration, default for permalinks) |
| Favorites & collections | Two distinct per-user collections. **Pasture** = working storage for horses ("store for later") — added via an explicit "add to pasture" action. **Save** = sentiment signal — small toggleable blue-ribbon icon on horses (→ Saved Horses) and on poems (→ Saved Poems). Both **private** — user sees their own; aggregate stats feed admin curation and popularity rankings; never displayed as public counts. The ribbon visually reads like an upvote but the "Save" label tells the user it's a private collection action |
| Print | Two `@media print` stylesheets: plain text (also = `.txt` download + image-card source for plain) and Victorian broadsheet (also = image-card source for fancy) |

### Top-level navigation (Phase 1)

Site-wide nav, not scroll-locked, user menu on the right:

- **Home** — `/`
- **Read Poems** — `/featured` (default destination)
  - Featured — `/featured` (hand-selected current rotation)
  - Browse — `/browse` (sortable / filterable feed)
  - Random — `/random`
- **Write Poems** — `/poetry` (one-page editor; alias `/write` planned)
- **Pasture** — `/pasture` (public default with random horses; renders your-pasture content when logged in)
- **Count** — `/count` (existing horse-counter feature, kept but de-emphasized in IA)

**User menu (right-hand side):**

- Logged out: **Sign In** button → `/sign-in`
- Logged in: username chip → dropdown with:
  - **Published Poems** — `/me/published` (own published poems; mirrors `/u/<slug>` content)
  - **Unpublished Poems (WIP)** — `/me/drafts` (drafts + submitted-not-yet-published)
  - **My Pasture** — `/me/pasture` (working horse collection)
  - **Saved Poems** — `/me/saved-poems` (blue-ribboned poems)
  - **Saved Horses** — `/me/saved-horses` (blue-ribboned horses)
  - **Edit Profile** — `/me/profile`
  - **Sign Out** — `/sign-out`

### Famous horses model
Two independent sources, both surfacing the same UI badge with a "why famous" caption on the more-info menu:

1. **IRL famous** — curated JSON: `data/famous_horses.json`. Caption examples: "Kentucky Derby winner", "Triple Crown winner", "Belmont winner", "Breeders' Cup Classic winner".
2. **Site-famous** — derived from real usage on poet.horse. Composite score from (a) appearances in published poems, (b) saves to user pastures, (c) favorites, and (d) permalink views. Top-N gets the badge. Caption: "#3 most-used horse on poet.horse".

A horse can be both. The badge merges both captions. **No voting** — the site never asks users to upvote. Rankings come from curated real-world facts or from real usage signals only.

---

## 3. Deferred / open

These exist as plans but won't be touched until the trigger condition fires. Listed here so they aren't forgotten.

- **counting.horse domain & redirect** — no decision needed for MVP; the existing horse-counter feature lives at `poet.horse/count`. Revisit if/when the domain is purchased.
- **Per-horse on-demand scrape** of pedigreequery (Cloudflare-aware Playwright session, polite rate-limit, dead-link blacklist) — **Phase 2**. Notes in `TODO.md` and braindump.
- **Real coat colors** — needs scraped data; defer until per-horse scrape is live. Hash-based pseudo-colors stay for now.
- **Public API exposure + OpenAPI spec** — internal-first design, public exposure in Phase 3.
- **Editor UX rethink** — Phase 2; needs a focused design conversation with multiple prototype UIs. Phase 1 ships a targeted pain-fix only.
- **Old poem import** from `data/poems/*.json` and the counting-horses Tumblr blog — best-effort one-shot script in Phase 1. Fresh start is acceptable if conversion is messy.
- **Lawyer review of ToS** — before monetization, not before launch. Plain-English placeholder ships in Phase 0.
- **Ambient field horses + emoji-sprinkle background** — Phase 2.
- **Multi-format line breaks** in poem schema — MVP encodes only `newline` breaks, with a publish-time warning when a poem has empty lines (intentional vs. strip).
- **Tumblr theme port** — keep current posting flow working but the matching Tumblr theme rebuild waits until the canonical site CSS is locked in. Phase 2.
- **Exquisite corpse mode** — Phase 3.

### Open design questions (resolve before phase start)

- **In-pasture horse interaction details** — confirmed shape (popover with name, link, poems-featuring, add-to-pasture, ribbon-save). Exact transition / placement / dismissal behavior is a Phase 1.7 design call.
- **Editor chip interactions (one-page builder)** — drag-primary vs click-primary vs hybrid. Marked for Phase 2 prototyping. Phase 1 keeps drag and adds a click-to-add fallback + drop zone.

### Items I made a default call on — flag if wrong

- **Internal poem ID:** UUID4 hex; **public short code:** 11-char base62 generated by `secrets.token_urlsafe(8)` then sanitized. Collision check on insert.
- **Counting feature in MVP:** stays at `poet.horse/count` with no redesign. Tumblr posting from there continues to work for admins.
- **Dictionary stays as a static file**, not migrated to SQLite. Lookups are O(1) via `word_index`; SQLite would only add overhead.
- **Clerk plan:** on the free tier (≤10k MAU). Re-evaluate if we hit the limit.
- **Pasture and Save are distinct collections** — Pasture is for working storage; Save (blue-ribbon) is for sentiment. They populate different per-user lists.
- **Save signals are private** — never displayed as public counts. Aggregates feed admin curation and popularity rankings only.

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

## Phase 0 — Foundations completion

0.1–0.4 are ✅ done (see "You are here" above). Remaining:

### 0.5 localStorage → account sync on first login `[sonnet · medium]`

- On first login, the client posts current `horse-stable`, `horse-poem-name`, `horse-poem-tumblr`, `horse-page-size` to a new `/me/sync` endpoint.
- Server merges into `stable_horses` and `users.preferences_json`. Client clears the local copies.
- "It already remembered" UX: show a one-time toast.
- Acceptance: build a stable of 3 horses while logged out, log in, see them on the server-side stable.

### 0.6 Plain-English ToS + privacy + data-deletion `[haiku · low]`

- New routes/templates: `/terms`, `/privacy`, `/data-deletion`. Plain-language summary at top, formal terms below. Link in footer.
- `/data-deletion` is a static instructions page (acceptable for smaller apps per Facebook OAuth requirements). Upgrade to webhook (`signed_request` verification + automated delete) later if needed for additional providers.
- Owner reviews wording before launch; lawyer review pre-monetization.
- Acceptance: all three pages render; footer link present site-wide.

---

## Phase 1 — MVP soft launch

Goal: poet.horse is a complete website that lets anyone compose, publish, and read horse poems. Tumblr is one optional outbound connector for the admin, scheduled via the cross-post queue.

### 1.1 Top-level navigation + IA `[sonnet · medium]`

- Implement the nav structure in `templates/base.html`: Home, Read Poems (with Featured/Browse/Random submenu), Write Poems, Pasture, Count.
- Right side: Sign-in button when logged out; username dropdown when logged in with sub-items:
  - Published Poems (`/me/published`)
  - Unpublished Poems / WIP (`/me/drafts`)
  - My Pasture (`/me/pasture`)
  - Saved Poems (`/me/saved-poems`)
  - Saved Horses (`/me/saved-horses`)
  - Edit Profile (`/me/profile`)
  - Sign Out
- Some destination pages render in later tasks (1.19 saves, 1.15 profile, etc.) — the menu links resolve to either real pages or a "coming soon" stub depending on phase order.
- Mobile: collapses to a hamburger; submenus expand inline.
- Acceptance: every top-level link resolves; user-menu items are reachable; submenu structure works keyboard-only and on touch.

### 1.2 Editor pain-fix: chip menu + drop zones + decoration strip `[sonnet · medium]` ✅ shipped 2026-05-16

After a design conversation with the owner the brief shifted from "click-to-add affordance + drop zone" to a more coherent **all-three-inputs-live** model (no modes, no gates):

- **Decoration strip.** Removed `<span class="legs">` and the `::before`/`::after` head/tail pseudo-elements from editor chips. Stable nth-child tilts and the per-poem-tile tilt are gone too — per the cross-cutting UI-vs-display commitment, editor chips keep only coat color and (for famous horses) shimmer. Body-part whimsy belongs in pasture-mode display surfaces.
- **Chip as button.** Every chip is a real `<button type="button">` with 44×44 minimum tap target, `aria-label`, and a `:focus-visible` outline. Keyboard activation is standard Enter/Space.
- **Canonical interaction: chip menu.** Tap (or Enter/Space on a focused chip) opens a small popover anchored to the chip with context-aware actions:
  - Stable chip: Add to poem (last line) · Send to My Pasture · Remove from stable
  - Poem chip: Move left · Move right · Move to last line · Send back to stable · Send to My Pasture · Remove from poem
  Menu is positioned with viewport-collision (`position: fixed`), focus-trapped via Arrow keys, ESC returns focus to the originating chip.
- **Drag preserved with click discrimination.** Pointer events with a 6 px movement threshold. Below threshold on release → chip menu opens. Past threshold → drag. The previous touch/mouse forks collapsed into a single `pointerdown`/`pointermove`/`pointerup` flow.
- **Ephemeral drop zones.** A drop-zone bar slides up from the viewport bottom only while `body.dragging` is set (Drop to last line · Send to My Pasture · Remove). No permanent UI furniture for users who never drag. `pasture` zone is hidden for anon users (they get a sign-in toast from the menu instead). Per-line `.drop-target` highlights are kept.
- **Pasture backend.** New `pasture_horses` table (per-user, name-keyed). `POST /me/pasture/add` accepts `{name, display, url}`, returns `{ok, added}`. Logged-out → JSON 401 with a sign-in message that the client surfaces as a toast.
- **Reuse target.** The chip-menu component is shaped to be reused for the 1.7 published-poem horse popover (same anchored-popover primitive, different item list).

Acceptance criteria met: every chip is keyboard-focusable; menu opens with Enter/Space; arrows navigate; ESC closes; drag still works on mouse and touch; the drop-zone bar catches drags from anywhere in the stable; menu actions work for both stable and poem chips on desktop and mobile viewports. Verified locally with the editor at /poetry, including 401 on logged-out pasture POST. Shipped as PR against `master`.

### 1.3 Tag taxonomy + selection UI `[sonnet · medium]`

- Seed `tag_categories` and `tags` with curated baselines (owner to edit before launch):
  - **Poem Type** (`single_select`): free verse, haiku, limerick, sonnet, couplet, ballad, ode, prose poem, concrete, found, other
  - **Theme** (`multi_select`): love, loss, nature, humor, hope, longing, anger, joy, memory, place, animals, the body, time, dreams, work, faith, other
  - **Linguistic Features** (`multi_select`): rhyming, blank verse, metered, alliterative, repetition, internal rhyme — **user-tagged at MVP**; auto-detection deferred to Phase 2+
  - **Content Warnings** (`content_warning`, multi_select with display-time consequences): sex, drugs and alcohol, violence, self-harm, death, slurs, mature themes
- Editor UI: one section per category. Single-select renders as a radio chip group; multi-select as a toggleable chip cloud; content_warning gets warning-styled chips with a tooltip explaining display behavior. Each section has a "suggest a new tag" affordance that submits to the pending queue scoped to that category.
- Acceptance: poems can be tagged across all four MVP categories; tagged poems show their tags grouped by category on the permalink.

### 1.4 Admin tag management `[sonnet · medium]`

- Admin route `/admin/tags`: list pending suggestions grouped by category. Approve / reject / merge into existing / move to a different category. Create new categories on the fly.
- Lightweight UI: drag tags between categories, type-to-merge.
- Acceptance: a user-suggested tag goes from poem submission → admin queue → approved (in chosen category) → available in the editor's picker for the next user.

### 1.5 Poem permalink + Open Graph `[sonnet · medium]`

- `/p/<short_code>` renders the poem with: title, attribution, tags, published date, view-mode toggle (plain / pasture — see 1.6).
- Open Graph tags: `og:title`, `og:description` (first line of poem + count), `og:url`, `og:type=article`, `og:image` (defer to Phase 2 image card; meanwhile use a static OG card).
- Acceptance: pasting a poem URL in Slack/Discord/iMessage shows a rich preview with the poem title and author.

### 1.6 Two-mode poem renderer (plain / pasture) `[sonnet · high]`

- Plain mode: utilitarian, semantic HTML, no animation, screen-reader friendly. Used as the default when the user has reduced-motion or has toggled reader mode.
- Pasture mode: grass background + decorated horse chips (current Tumblr-theme styling, ported in). Default for permalink visits.
- Toggle button in the poem header, persisted to localStorage (and to `users.preferences_json` if logged in).
- Acceptance: a permalink loads in pasture by default; toggle persists across sessions.

### 1.7 Horse popover in pasture mode `[sonnet · high]`

- Click/tap a horse chip in pasture-mode display → popover with:
  - Horse name
  - Pedigreequery link
  - **Blue-ribbon "Save" toggle** — small icon, top-right of the popover. Toggled on = horse is in Saved Horses. Compact, doesn't take a full row.
  - **"Add to my pasture"** button — explicit row action (or "Remove from pasture" if already in).
  - "Poems featuring this horse" — list of permalinks; shows up to N, links to `/horse/<slug>` for full list once Phase 2.10 ships.
- Logged-out behavior: both the ribbon and the pasture button trigger an inline sign-in prompt — "Sign in to save horses to your collection." / "Sign in to add horses to your pasture." Distinct messages so the two actions feel distinct.
- Keyboard-accessible, focus-trapped while open, ESC to close.
- Acceptance: click any horse on a permalink → popover; logged-in ribbon and pasture actions both work and persist; logged-out prompts fire with the right copy per action; clicking outside dismisses.

### 1.8 Featured / Browse / Random `[sonnet · high]`

- **`/featured`** — admin-curated current rotation. Pinned poems display in order set by admin. New `featured` table or `poems.featured_at` column + `featured_order`.
- **`/browse`** — paginated feed (50/page) with:
  - **Sorts:** newest first (default), oldest, by title (A–Z), by author (A–Z)
  - **Filters (combinable, as chips):** tag (any category), poem type, theme, linguistic feature, author/poet, contains horse (autocomplete dictionary lookup), **time-of-day band** (e.g. "12am–6am", with custom range picker), date range
- **`/random`** — 302 to a random published poem; "another one" button.
- Acceptance: filters combine; URL state is shareable (`/browse?tag=haiku&hour=3-5&sort=newest`); time-of-day filter respects the poem's stored local time.

### 1.9 Empty-line warning at publish time `[haiku · low]`

- Before submission, if any line in the poem is empty, show a modal: "Empty line detected — keep as a stanza break, or strip?" with two buttons.
- Acceptance: submitting with empty lines triggers the modal; choosing "strip" removes them client-side before POST.

### 1.10 Export: plain text copy, HTML copy, .txt download `[sonnet · low]`

- Buttons on the permalink page: "copy as text", "copy as HTML", "download .txt".
- HTML copy includes minimal inline styling so it survives paste into rich-text contexts.
- Acceptance: each button works in Chrome and Safari.

### 1.11 Plain-text print stylesheet `[sonnet · medium]`

- `@media print` for plain mode: serif font, generous margins, poem centered, attribution caption, `poet.horse` URL in footer, Weatherhead citation in fine print at the bottom.
- "Print" button on permalink invokes `window.print()`.
- Acceptance: print preview on a poem looks like a poem on a page; no UI chrome bleeds through.

### 1.12 Reader-mode toggle (site-wide) `[sonnet · medium]`

- Always-visible toggle in header. Sets a `prefers-plain` localStorage flag (and `users.preferences_json` if logged in).
- When set, every renderer uses the plain path. Respects `prefers-reduced-motion` and `prefers-contrast` automatically.
- Acceptance: toggle on → permalink loads in plain by default; refresh persists choice.

### 1.13 Admin moderation queue overhaul `[sonnet · high]`

- Rework `/submissions`: queue is poem-first, not Tumblr-post-first. Each row: poem preview (plain), suggested tags, attribution, "publish to site" / "publish + queue for cross-post" / "edit and publish" / "reject".
- **Inline tag editing:** suggested tags appear inside the review card. Admin can approve / reject / move-to-different-category / merge with an existing tag *without leaving the queue*. New-category creation also inline.
- Publish flips `poems.status` to `published`, sets `published_at`. Cross-post button flags the poem for the cross-post queue (see 1.20).
- The existing counter-submission queue stays as-is (it's a different flow), routed under `/admin/counter-queue` or similar.
- Acceptance: a public poem submission lands in the admin queue; admin clicks "publish" → poem appears on `/browse` and at its permalink; tag edits applied inline persist.

### 1.14 Report button + report queue `[sonnet · medium]`

- "Report" button on every poem permalink and on poet display names. Logged-out users can report (rate-limited by IP).
- Admin route `/admin/reports`: list pending, approve (hide poem / rename slug / delete) or dismiss.
- "One-click hide pending review" admin button on poems.
- Acceptance: report submitted → appears in admin queue → admin actions take effect.

### 1.15 Poet profile `/u/<slug>` `[sonnet · medium]`

- Public page: display name, slug, joined date, poems published (paginated reverse-chrono), small "edit profile" link if owner is viewing their own.
- Owner can edit display name (slug is permanent post-Phase-0).
- Acceptance: visiting a slug shows that poet's published poems; anonymous-poem authors have no profile.

### 1.16 RSS feed `[sonnet · low]`

- `/feed.xml` for all published poems (most recent 50). `/feed.xml?tag=haiku` and `/u/<slug>/feed.xml` for filters.
- Acceptance: feed validates at validator.w3.org/feed; opens in a reader.

### 1.17 Rate limiting `[sonnet · low]`

- Add `flask-limiter` (Redis if VPS has it, in-memory otherwise). Limits: poem submission (5/hour anon, 30/hour logged-in), reports (3/hour per IP), search (60/min), API endpoints (per-route).
- Acceptance: exceeding the limit returns 429 with retry-after header.

### 1.18 One-shot import of existing data `[sonnet · medium]`

- `tools/import_legacy.py`: pulls `data/poems/*.json` (the current store) into SQLite as published poems with their existing IDs as `short_code` (collision-checked). Optionally pulls poems posted to the counting-horses Tumblr via the API and imports those too, attributing to "anonymous (legacy)".
- Best-effort; failures logged not raised.
- Owner runs once before DNS cutover.
- Acceptance: post-run, `/browse` shows a populated feed.

### 1.19 Save (Blue Ribbon) + Pasture collections `[sonnet · medium]`

Two separate per-user collections, each backed by its own table.

- **My Pasture** — working storage for horses. Schema: `pasture_horses` (user_id, horse_name, added_at). Populated by the "add to my pasture" action in 1.7 popover, in the editor "→ pasture" chip action, and via the pasture-search mode (2.9).
- **Saved Horses** — sentiment collection. Schema: `saved_horses` (user_id, horse_name, saved_at). Populated by the **blue-ribbon "Save" toggle** in the 1.7 popover (and anywhere else a horse chip appears with full UI).
- **Saved Poems** — sentiment collection for poems. Schema: `saved_poems` (user_id, poem_id, saved_at). Populated by the same **blue-ribbon "Save" toggle** placed on poem permalinks. Visual treatment: blue-ribbon icon + "Save" label (text-paired so the user reads it as a private-collection action, not a public upvote).
- **`/me/saved-horses`** and **`/me/saved-poems`** — list pages, paginated, with "remove" toggles per item.
- **`/me/pasture`** — list page (also the logged-in destination for top-nav Pasture).
- **Private:** none of these counts are surfaced publicly. Admin sees aggregates in `/admin/stats` for curation.
- Saves + pasture additions + view counts feed the site-popularity score for horse and poem ranking (Phase 2.12).
- Acceptance: logged-in user can independently toggle Save and add to Pasture for any horse; can Save any poem; each collection has its own `/me/*` page; admin sees aggregate counts.

### 1.20 Cross-post queue (admin-flagged) `[sonnet · high]`

- New table: `cross_post_queue` (id, poem_id, platform: tumblr/bluesky/mastodon/threads/x, status: pending/posted/failed, scheduled_for, posted_at, response_json).
- Admin flags a poem for cross-posting per platform from the publish flow (checkboxes in 1.13). Queue picks them up.
- **MVP scope:** Tumblr connector only (existing code adapted). Other platforms (Bluesky/Mastodon/Threads/X) ship in Phase 2.15.
- Schedule: a single cron tick (e.g. once an hour) processes pending items, one platform per run. Schema supports per-platform schedules later.
- Automatic poem selection (the bot picks unflagged poems) is deferred. **Admin flag → queue → post** only at MVP.
- Acceptance: admin flags a poem for Tumblr cross-post; on next cron tick it posts; status flips to `posted`. Failures log and don't block the queue.

### 1.21 Soft sign-in prompts `[sonnet · low]`

Three quiet touchpoints, no modals:
- **Inline near the stable** in the editor: small text "Sign in to save horses for later." Permanent but understated.
- **Toast after first successful poem submit** (anonymous): "Your poem is in the queue. Sign in next time to track it." Auto-dismisses; not blocking.
- **Action-gated prompt:** "add to pasture" / "favorite" / "save draft" while logged out → inline prompt at the action site, not a redirect.
- Acceptance: all three appear in their contexts; none of them block flow; can be dismissed permanently per-user via a `dismissed_prompts` localStorage flag.

### 1.22 Attribution footer + Ko-fi support `[sonnet · low]`

- Site-wide footer (every page, plain mode and pasture mode):

  > "The best way to read a poem is to pretend each line is the name of a horse; so the poem is just a list of horses." — [@weeatherhead](https://x.com/weeatherhead/) ([Andrew Weatherhead](http://www.andrewweatherhead.org/)), [Mar 19, 2013](https://x.com/weeatherhead/status/314089933906264066)

  Note: keep the `andrewweatherhead.org` link as `http://` — the site doesn't support HTTPS (verified 2026-05-15). The footer should be marked up as a real `<blockquote cite="...">` + `<cite>` so it gets nice typography.

- **Ko-fi link** in the footer next to the clover emoji 🍀 — plain `<a href="https://ko-fi.com/G2G81ZF3IA">`. No floating widget (Ko-fi's Widget_2.js injects layout-breaking styles). Clover-emoji touchpoints in Phase 2.13 reuse the same anchor.
- Acceptance: footer visible on every page; Weatherhead citation renders as a styled blockquote; Ko-fi link is keyboard-reachable and opens in a new tab.

### 1.23 GitHub Actions deploy `[sonnet · medium]`

- `.github/workflows/deploy.yml`: on push to `master`, ssh to VPS, `git pull`, `uv pip install -r requirements.txt`, `systemctl --user restart poet-horse.service`. Use repo secrets for SSH key.
- Acceptance: pushing to `master` deploys and the service restarts within 30s.

### 1.24 DNS cutover + PA shutdown `[haiku · low — owner action]`

- (DNS already cut. PythonAnywhere app still running.)
- Once new site has been live for a few weeks with no regressions, shut down the PA app. Optional: configure PA to redirect to poet.horse.

---

## Phase 2 — Beta & feedback (after Tumblr / Metafilter soft launch)

Triggered when soft launch is live and traffic / feedback is flowing. Tasks here can be ordered freely.

### 2.1 Editor UX rethink (multiple toggleable styles) `[opus · high]`

- Owner has flagged the editor needs a real redesign — less drag-dependent, more thoughtful affordances.
- Two-stage task:
  1. **Design doc + prototypes** (`docs/editor-redesign.md`): produce 2–4 distinct UI styles. Input model alternatives — keyboard/click-to-add primary, sortable list, free-text-with-autocomplete, drag-as-current, hybrids. Build runnable prototypes for each (separate routes under `/poetry/proto/<style>`). Get owner sign-off.
  2. **Implementation + style toggle:** ship the winning styles as togglable options. User preference stored in `users.preferences_json.editor_style` (and localStorage for anon).
- Accessibility plan, mobile vs desktop ergonomics, and reduced-motion behavior are part of the design doc.
- Acceptance: design doc merged; ≥2 styles available in production; user can switch and choice persists.

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

### 2.5 "Horsified HTML" copy + embed.css `[sonnet · medium]`

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
- 404s surface to the user as "horse not found" in the popover and add the name to the exclusion list.
- Acceptance: clicking "more info" on a horse fetches and caches its PQ data within 3s; second click is instant.

### 2.8 Real coat color encoding `[sonnet · medium]` (depends on 2.7)

- Map PQ color codes (`b`, `ch`, `gr/ro`, `blk`, etc.) to CSS variables.
- Use scraped color when present; fall back to hash-based for unknowns.
- Acceptance: Black Beauty renders dark.

### 2.9 Pasture-search mode (whimsy opt-in) `[sonnet · high]`

- New toggle on the horse-search UI in the editor (and `/pasture`): switch search-results display from list to a grass-styled pasture. Results scatter as horse chips (random walk optional, see 2.14). Drop zones around the pasture: "→ stable", "→ my pasture", "remove". Per-chip context menu: more info / add to current line.
- Per the cross-cutting commitment about UI/display separation — this is opt-in whimsy, never the default in the editor.
- Acceptance: toggle flips list ↔ pasture display; actions on chips reach the same destinations as the list mode; preference persists.

### 2.10 Browse pages: per-horse + per-tag `[sonnet · medium]`

- `/horse/<name-slug>` — all poems featuring this horse + horse metadata (registry, country, birth year, scraped fields if any).
- `/tag/<tag-slug>` — all poems with this tag.
- Acceptance: each page paginates, sorts (newest / most-favorited-private / random), and is link-shareable.

### 2.11 Search inside poems `[sonnet · high]`

- SQLite FTS5 virtual table on `poems(title, lines_text, author_display_name, horse_names_concat)`.
- `/search?q=...` UI with filters by tag, by poet, by horse-in-poem.
- Acceptance: searching for "rosebud" returns poems containing horses named Rosebud, poems with "rosebud" in the title, and poets named Rosebud.

### 2.12 Famous-on-poet.horse popularity stats `[sonnet · medium]`

- Nightly cron computes a per-horse usage score from real signals: (a) count of distinct published poems containing the horse, (b) count of users with the horse in their pasture, (c) count of poems featured that contain the horse, (d) permalink views. Tunable weights, default equal.
- Top-N gets the "site-famous" badge; cache the rolling list in `data/site_famous.json`.
- Merge with IRL famous list when surfacing the more-info menu (e.g. "Kentucky Derby winner · #3 most-used on poet.horse").
- Acceptance: the more-info menu on a popular horse shows both reasons; rankings shift sensibly as new poems are published.

### 2.13 Ambient field horses + emoji-sprinkle background `[sonnet · high]`

- z-index layering per spec: base color → SVG grass tile (seamless) → emoji sprinkle (☘🍀🍄‍🟫🍄🌾🪾🌳, varied sizes, faux perspective) → styled horses → UI layer.
- A few horses gently random-walk in the background of pasture views and the homepage hero.
- Specific font fallback chain for the emoji-sprinkle layer to maintain consistent style across platforms.
- **Clover emoji touchpoints** = Ko-fi link targets (clickable, tooltip "Support poet.horse on Ko-fi").
- Respect `prefers-reduced-motion` (no animation when set).
- Acceptance: pasture view has a believable field; reduced-motion users see static; clovers are interactive and discoverable.

### 2.14 Cross-post connectors: Bluesky, Mastodon, Threads, X `[sonnet · high]`

- Each platform = a new connector module. Same queue contract as the Tumblr connector from 1.20.
- Per-platform setup notes documented in `docs/connectors/<platform>.md`. Threads and X may be the hardest (rate limits, API access).
- Image-card export (2.3) feeds platforms that need a media attachment.
- Acceptance: admin can flag a poem for any subset of platforms at publish time; queue processes each on its schedule; failures don't block siblings.

### 2.15 Tumblr theme port (after web CSS is locked) `[sonnet · medium]`

- Once the canonical site CSS is stable, port the styling into a new Tumblr theme. Address the class-attribute-stripping issue (`TODO.md`) — likely via data-attribute selectors or inlined structural CSS.
- This unblocks the visual experience for Tumblr users who view themed blog pages directly (most won't — they view the dashboard).
- Acceptance: a poem reblogged from poet.horse to the Tumblr blog renders with horse styling on the themed blog page.

### 2.16 Three-concept UI cleanup: Stable / Your Pasture / Pasture mode `[sonnet · medium]`

- By Phase 2 these concepts exist organically; this task is the deliberate disambiguation pass:
  - **Stable** — the working area for the current poem (existing).
  - **Your Pasture** — per-account collection of saved horses (Phase 1.19; this task adds the `/pasture` rendering polish and "load from pasture" button in the editor).
  - **Pasture mode** — display convention (Phase 1.6 plus 2.13 ambient layer).
- Acceptance: each concept is distinct in UI copy and code; user testing shows no terminology bleed.

---

## Phase 3 — Growth (if concept has legs)

Triggered when sustained traffic justifies the lift.

### 3.1 Exquisite corpse mode `[opus · high]`

- Collaborative poetry mode: a poem is built line-by-line by different users, each seeing only the previous line (classic exquisite corpse). Phase-start design doc needed; this is a real product surface.
- Open questions to resolve before code: how lines are claimed (FCFS? lobby? invite?), abandonment / timeout behavior, attribution (per line? collective?), moderation surface, anonymous participation policy.
- Acceptance: design doc merged, sign-off received, then implementation.

### 3.2 Hall of Fame `[sonnet · medium]`

Two distinct halls, same principle as the famous-horses model: rankings come from curated real-world facts or real site-usage signals — never from voting.

- **Curated hall** at `/hall-of-fame/curated`: permanent archive of poems that have appeared on `/featured`. Admin can pin additional poems (e.g. featured by Metafilter, included in an anthology, won an off-site contest). Caption explains why.
- **Popular hall** at `/hall-of-fame/popular`: derived from real usage signals — view counts on permalinks, copy/export button presses, favorites (private), inclusion of constituent horses in user pastures. Tunable weights; nightly recompute.
- Acceptance: admin can pin / unpin a poem in the curated hall with a caption; the popular hall updates daily from logged signals.

### 3.3 Public read API + OpenAPI spec `[sonnet · high]`

- Promote internal endpoints: poem by ID, poems by poet, poems by horse, horse-database lookup, random poem, random horse.
- Generate `openapi.yaml`. Serve `/api/docs` (Swagger UI).
- Per-key rate limits via API tokens (admin-issued for now).
- Acceptance: API docs are public; an external curl call returns JSON.

### 3.4 Horse database public download `[haiku · low]`

- `/data/horses.json.gz` static download with a license file. Credit/backlink culture.
- Acceptance: file is downloadable; license clearly states terms.

### 3.5 Independent VPS migration `[sonnet · medium — partly owner action]`

- If radio-station VPS becomes inappropriate or traffic warrants it: provision Hetzner/DigitalOcean (~$6/mo), reuse the GitHub Actions deploy (just swap secrets), DNS cutover.
- Acceptance: same site, new IP, no downtime > 5 min.

---

## Phase 4 — Monetization (if revenue threshold met)

Trigger: ~$20/mo sustained tip income, or interest from a small ad partner. (The Ko-fi widget already ships in Phase 1.22 — this phase is the *framework* around it.)

### 4.1 Ko-fi tip jar polish `[sonnet · low]`

- Promote the Ko-fi presence: dedicated `/support` page describing the project and ask, FAQ on hosting costs and how funds are used.
- Acceptance: `/support` page live; footer link present.

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
- **The dictionary stays a fact, not a vibe.** Don't filter horses by name appropriateness — moderation happens on poems, not on the source data.
- **Admin work is rare and explicit.** Don't automate admin actions, don't hide them behind heuristics. Curation is the product.
- **Web 1.0 ethos.** Static where possible, light JS, view-source-able. The audience will notice.
- **No upvotes, no engagement metrics surfaced to users.** Save (blue-ribbon) counts and Pasture-add counts are **private to the user and admin only** — never displayed publicly. Any "popular", "famous", or "hall of fame" ranking comes from curated real-world facts or from real site-usage signals (poem occurrences, Pasture adds, Saves, view counts, exports). Never from a thumbs-up button.
- **UI vs display separation.** Functional UI (editor, search, navigation) stays utilitarian — color palette and grass background as the only decorative elements. Whimsy (decorated horse chips, ambient field, random-walk) lives in display surfaces or opt-in modes. The editor is the canonical example: chips keep color + shimmer but no body parts.
- **Tumblr is one connector among many.** The website is the canonical source of truth. Tumblr-specific work (theme port, posting code) is never on the critical path.

---

## 6. How to use this doc

When opening a fresh session to do work, point Claude at the relevant section:

> "Implement task 1.5 from ROADMAP.md."

Claude reads the section, applies the suggested model + effort, and returns a PR-shaped change. The acceptance criteria are the contract.

When a task uncovers something this doc didn't anticipate, update this doc in the same PR — don't let drift accumulate.
