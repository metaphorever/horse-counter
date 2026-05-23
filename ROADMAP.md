# poet.horse — Roadmap

Navigation doc for the project. Full pre-migration history lives in `sessions/pre-migration-history.md`; this file is the live map going forward.

---

## 🛑 Active blockers

None.

---

## Phase map

### Phase 0 — Foundations · ✅ closed

VPS provisioning, SQLite schema, short-code permalinks, Clerk auth, localStorage→account sync, ToS/Privacy/Data-Deletion pages. Site has its shell.

### Phase 1 — MVP soft launch · 🟡 mid-flight

**Shipped:**
- 1.1 Top-level nav + IA
- 1.2 Editor pain-fix: chip menu + drag + pasture backend
- 1.3 Tag taxonomy + attribution + trust scaffold
- 1.5 Poem permalink renderer + Open Graph
- 1.6 Two-mode poem renderer (plain / pasture)
- 1.22 Attribution footer + Ko-fi support
- Nav/footer chrome polish (2026-05-16)
- **1.6.1 Hotfix — Restore submission flow end-to-end** (2026-05-18) — `init_db()` at app startup, `/browse` poem index stub, mobile chip touch-drag fix
- **1.7 Horse popover in pasture mode** (2026-05-18) — horse_occurrences/pasture_horses/saved_horses tables, popover with save/pasture/poems-featuring, focus-trapped + ESC/outside-click dismiss, logged-out prompts, `/p/<short>` now renders full permalink template
- **1.8 Featured / Browse / Random** ✅ — two-tier tag system (public + admin-only `tag_categories.admin_only`), `featured_sections` table, `/browse` with pagination/sort/tag-filter/attribution-filter, `/random` redirect, `/featured` page driven by admin-curated sections, `/admin/featured` management page, per-poem admin tag editor on poem page. Built out of order across earlier phases; verified working by Clover (2026-05-21).
- **1.9 Empty-line warning at publish** ✅ — mid-poem empty line detection at submit time; modal warning with "Remove empty lines" / "Keep them" choice; "Remember my choice" checkbox persists preference to localStorage (anonymous) or `/me/preferences` (logged-in). Verified by Clover.
- **1.10 Export: copy as text / HTML / .txt** ✅ (2026-05-18) — three buttons in the poem footer: copy plain text (horse names), copy HTML chip markup, download .txt with title/attribution/URL header. All client-side.
- **1.11 Plain-text print stylesheet** ✅ (2026-05-19) — `@media print` stylesheet: Smokum corner-logo masthead, Abril Fatface title, IM Fell English body in small-caps, Playfair Display SC attribution/tags, turnover (hanging) indent on poem lines, thin underline separating horse names, colophon note + permalink. New fonts loaded site-wide as shared toolbox for future web use. Verified by Clover.
- **1.25 Nav / IA polish** ✅ (2026-05-19) — labels: "Drafts", "My Poems"; removed "Home" nav item; Featured/Browse/Random promoted to top-level; `/` redirects to `/featured`.
- **1.26 Horse search area rework** ✅ (2026-05-19) — short names link → button; random horse button in search panel; pasture horses button with pagination; compact help/how-to button.
- **1.27 Save draft from poem builder** ✅ (2026-05-19) — Save Draft button + modal; draft-centric stable model; SQLite-backed drafts with stable_json + full metadata; `/me/drafts` live page; horse popover gains "Add to draft stable" picker; anon `horse-draft` localStorage shape with migration; `syncLocalToAccount` saves anon draft on first login. Removes `stable_horses` table + `/me/stable/*` routes.
- **1.28 Draft polish: popover quick-create + editor auto-save redesign** ✅ (2026-05-20) — Popover: 0-draft → inline quick-create form; 1+-draft → list + "Add to new draft ▸" expander. Editor: page-load picker when 1+ drafts; auto-save (immediate on add/remove, 7s debounced on drag); "Currently editing [NAME] [Change Draft ▾]" strip; renamed buttons (Clear Stable / Clear Poem / Edit Details / Post Poem); clear dialogs with destination options. PR #43 + hotfix PR #44 (admin user fix). Holds 1–9 verified by Clover (2026-05-21); hold 10 (anon flow) deferred.
- **1.16 RSS feed** ✅ (2026-05-21) — shipped in PR #45 alongside 1.17 + 1.21
- **1.17 Rate limiting** ✅ (2026-05-21) — shipped in PR #45 alongside 1.16 + 1.21
- **1.21 Soft sign-in prompts** ✅ (2026-05-21) — shipped in PR #45 alongside 1.16 + 1.17
- **1.14 Report button + report queue** ✅ (2026-05-21, verified) — report modal on poem permalink; `reports` table; `/admin/reports` queue with action/dismiss; thank-you auto-dismisses after 15s
- **1.15 Poet profile `/u/<slug>`** ✅ (2026-05-21, verified) — full profile with bio poem picker, published poems list, links; `/me/profile` edit page; `bio_poem_id` column on users
- **1.19 Save (Blue Ribbon) + Pasture collections** ✅ (2026-05-21, verified) — `saved_poems` table; ribbon button on poem permalink; `/me/saved-poems`, `/me/saved-horses`, `/me/pasture` list pages

**Remaining (rough order):**
- 1.12 Three-mode display system — replace binary plain/pasture with: **Plain** (workhorse/admin/accessibility — field is decorative bg; each independent content area is a count-page-style pinned note box with pin emoji; horse chips colored+shimmer, no body parts; bumped text/touch targets; reuses pasture CSS simplified), **Pasture** (field IS the surface; no container; text/UI elements separated from bg via contrasting color outline — specific color TBD at prototype stage; non-horse text de-emphasized; UI ornate; full body parts + walking horses), **Reader** (off-white page; typographic; print-stylesheet aesthetic on screen; woodprint-style button borders; no field). Site-wide persistent preference, server-resolved. Stored `"plain"`/`"pasture"` preference values can be discarded/reset on migration — no user-data concern (solo use). Requires renderer rearchitecture; mobile pasture layout (floating text on narrow viewport). Spec session required before implementation. Text styling in reader/pasture confirmed as prototype-first — commit only after Clover reviews options. `[opus · high]`
- **1.13 Admin moderation queue overhaul** ✅ (2026-05-22, verified) — chip render in queue cards; submitter tags as removable chips by default with "Edit tags" toggle for full picker; publish explicitly sets admin's tag selection; reviewer ID wired to Clerk user; full preview link per card
- **1.13.1 Trust score system** `[sonnet · medium]` — Pairs with 1.13. Integer trust score per user (column on `users`), starts at 0 for new accounts and anonymous/pseudonymous. Scoring: +1 per admin-approved poem where no tag edits were made; -1 per poem where admin edited tags before/during approval. Admin can manually override score from the user page. Admin sets per-action thresholds stored in DB (not hardcoded), e.g. `auto_post_threshold = N` → users with trust ≥ N bypass the queue and post instantly. Default threshold 0 = open posting for new/anon users; raising it gates newcomers when abuse spikes. Enables: "let loyal Tumblr fans post freely while blocking bad actors" without a code deploy. Depends on 1.13 (queue overhaul ships the approval/edit event hooks needed to update scores). Current behavior (admin = instant, everyone else = queue) is the threshold-0 / threshold-∞ special case and does not need to change until this ships.
- ~~1.18 One-shot import of legacy data~~ — **STRUCK 2026-05-17.** Fresh launch instead; see `spec/product.md` "Permanently out of scope." Old poems stay on Tumblr / wherever they already are; nothing imported into the new explicit-ToS environment.
- 1.20 Cross-post queue (admin-flagged, Tumblr connector) `[sonnet · high]`
- **1.23 GitHub Actions deploy** ✅ (2026-05-22, verified) — `appleboy/ssh-action`; git pull + uv pip install + systemctl --user restart on every push to master
- 1.24 DNS cutover + PA shutdown `[haiku · low — owner action]`
- **1.4 Admin tag management** ✅ (2026-05-22, verified) — pending tag review + approve/reject; tag rename/deactivate/safe-delete; category rename/safe-delete; unified view at `/admin/featured`
- **1.29 DRY poem renderer** `[sonnet · medium]` — Jinja2 macro for horse chip (coat + rev + famous + link mode) and poem line loop; used in poem.html, poem_queue.html, user_profile.html (fixes bio poem's missing coat/rev/famous styling); update pasture + saved-horses routes to send full horse data and use chip macro; add turnover indent (`padding-left: 2em; text-indent: -2em`) to screen `.poem-line-out` (currently print-only). Sets up 1.12 mode parameter cleanly.
- **Style pass session** — focused styling session before beta (fancy/plain/high-contrast/typography-only print modes side-by-side; restore decorated editor chips; **wandering pasture/saved-horses layout**: horse chips scattered at random 2D positions with sort modes — date added / alphabetical / random / wandering; all non-wandering modes use column layout; fix green font color on `/me/saved-horses` and `/me/pasture`; bio poem on `/u/<slug>` should render with full poem styles consistent with user display settings). Pre-beta, not mid-feature.

### Phase 2 — Beta & feedback · ⏳ pending soft launch

Editor UX rethink (opus), explicit/mature display, image-card export, fancy broadsheet print, horsified HTML embed, oEmbed, per-horse PQ scrape (Cloudflare-aware), real coat colors, pasture-search mode, per-horse/per-tag browse pages, FTS5 search, site-popularity stats, ambient field horses, Bluesky/Mastodon/Threads/X connectors, Tumblr theme port, three-concept disambiguation pass.

### Phase 3 — Growth · ⏳ pending sustained traffic

Exquisite corpse mode, Hall of Fame (curated + popular), public read API + OpenAPI, horse-database public download, independent VPS migration.

### Phase 4 — Monetization · ⏳ pending revenue threshold

Ko-fi tip-jar polish, Carbon-style static ads, ad-free supporter keys, supporter cosmetic flair, lawyer review, merch/anthology exploration.

---

## Backlog

Surfaced items not yet committed to a phase. Promote to a phase when ready.

- **Editor button layout tweaks** — "Wrangle a Poem" page: (1) Clear Poem button should match Clear Stable styling (danger-colored, wide, short); (2) Post Poem and Edit Details buttons should move below the poem area under the draft picker; (3) "Poem" and "Stable" section labels should be the same font size. Slot into the pre-beta style pass session.
- **Tumblr post CSS desync** — new posts lose chip structural styling because Tumblr appears to strip `class` attributes; `--bg`/`--fg` inlined vars survive but `.horse-link` body-shape rules don't. Fix path: data-attribute selectors or inlined structural CSS. Deprioritized — most Tumblr viewers use dashboard (CSS stripped there anyway). Revisit after website CSS is locked. (Originally tracked in pre-migration TODO.md.)
- **Link validator** for `short-names-validation.html` and eventually the full dictionary — Cloudflare-aware Playwright session, polite rate-limit, page-content check for "not found", outputs annotated HTML or `data/link_validation.json`. Pilot with the short-names list (1362 horses). (Originally TODO.md.)
- **Sync `data/horse_overrides.json` from production back to git** — canonical overrides file lives on the server and gets edited in prod; doesn't automatically flow back. Options: one-click admin export, cron commit, or deploy-time pull-first hook. (Originally TODO.md.)
- **Ambient background horses** — a few chips in the SVG grass behind working areas (z-indexed so they never overlap UI); bonus walk-cycle. Subset of Phase 2.13. (Originally TODO.md.)
- **Auth redirect: return-to-origin + modal sign-in** — after sign-in/account creation, user should land back where they were (e.g. mid-poem in the editor) rather than the homepage. Standard `?next=` pattern: stash the destination URL before redirecting to sign-in, restore it after Clerk verify completes. Pair with a modal sign-in flow so auth doesn't break editor state at all. Belongs in a Clerk-focused session; noted 2026-05-19 as something that should have been handled during Phase 0 Clerk integration.
- **Follow other posters** — low-key social-graph primitive: follow a poet, see a feed of their published poems. No DMs, no friend requests, no mutual handshake. Surfaced during 2026-05-17 product-spec interview as a net addition to scope.
- **Profile bios made of horses** — required: profile bios must obey the constraint too. On-brand enforcement of the site's central rule. Pair with 1.15 (poet profiles).
- **Profile external links** — short list of links on a profile to personal sites / social platforms / contact methods. Explicit answer to "no DMs on poet.horse" — take connection off-platform. Pair with 1.15.
- **"Response to" attribution variant** — extend the Phase 1.5 attribution flag (`inspired_by_text` / `inspired_by_url`) so the URL can point at a poet.horse permalink and the UI reads as a reply rather than an external citation. Tentative — "fun and pretty low cost to build in with the current structure but it doesn't need to block anything currently in dev." Doesn't bump 1.7–1.21.
- **Remove PIN admin auth** — Clover, 2026-05-17: *"PIN can be pruned out whenever now that Clerk is online."* Replace the dual-auth surface (`app.py:122` `_is_admin()`) with a single Clerk-only role check. Resolves the "Clerk role and PIN admin are independent" open design question. Coordinate with: adding admin-promotion UI so Clerk users can be elevated without DB surgery.
- **Remove legacy JSON submission backend** — Clover, 2026-05-17: *"same with old json submission path."* Delete `submissions.py` (JSON queue) and the associated admin surfaces (`/submissions`, `/queue`, etc.); SQLite-backed poem submissions become the only path. Resolves the "Dual submission backends" open design question. Order: do this after 1.13 (admin moderation queue overhaul) which already plans the new poem-first review UI.
- **Web typography pass using print font toolbox** — 1.11 loaded Smokum, Abril Fatface, IM Fell English, and Playfair Display SC site-wide. Candidate uses on screen: Abril Fatface for nav/site identity elements; IM Fell English for plain-mode poem body; Playfair Display SC for attribution lines. Slot into the pre-beta style pass session — don't apply piecemeal.
- **Fancy picket fence print ornament** — a small centered fence vignette (embellished picket tips, a few posts wide) used as a decorative separator in the Phase 2 Victorian broadsheet print mode. Not a full-width repeating rule — a single ornamental cut, like a printer's fleuron. Held out of the plain-text print stylesheet (1.11) deliberately: wrong register there. Belongs in the broadsheet mode where the decorative weight is matched throughout.
- **Per-poem line alignment + freeform positioning** — poet-controlled display formatting for artistic intent. Two parts: (1) per-line or per-poem alignment toggle (left / center / right), needed for concrete poetry where shape is meaning; (2) freeform mode that records relative pixel positions per horse, enabling arbitrary visual layouts. Both touch `lines_json` shape and the renderer. The freeform mode is a significant data model change and a new editing paradigm. Slot near or after Phase 2 editor rethink (2.1). Do not conflate with the Phase 1.9 empty-line warning — that's a publish-time data hygiene check; this is a display/authorship feature.
- **SVG logo (`poet-horse.svg`) in web and print** — replace the Smokum-typeset "poet.horse" text in (1) the site nav/header and (2) the print stylesheet's `.print-masthead` with the custom SVG logo (horse-head and horse-tail on the "h" of "horse", underline). SVG already committed to repo root as `poet-horse.svg`. Slot into the pre-beta style pass session alongside the web typography pass — both touch site identity elements.
- **Saved Horses nav button** — add a "Saved Horses" button next to Short Names / Random / My Pasture in the horse search area; logged-in only; loads user's saved horses. Slot into 1.29 or style pass.
- **Horses from published poems auto-added to pasture** — design pivot from the original spec (pasture = explicit-add only). Clover's intent: pasture = every horse name you have ever published, plus explicit adds. Requires a backfill event on poem publish/approve. Slot after 1.29 (which updates pasture data flow anyway).
- **Tags in Edit Details not carried to Post Poem** — tags saved during "Edit Details" are not pre-populated when the user clicks "Post Poem." Proposal: unify into one flow with different terminal actions (save draft / post). Needs UX spec before implementation.
- **Suggested (new) tags not surfaced in mod queue** — 1.13 shows existing pending tags as chips in the queue card, but user-proposed new tag names are not surfaced. Admin should see proposed new tags alongside the poem and be able to approve the tag and the poem together. Gap in 1.13.

---

## Open design questions

Resolve before the relevant phase starts.

- **In-pasture horse interaction details** — popover shape confirmed (name, link, poems-featuring, add-to-pasture, ribbon-save). Exact transition / placement / dismissal behavior is a Phase 1.7 design call.
- **Editor chip interactions (one-page builder)** — drag-primary vs click-primary vs hybrid for the Phase 2 rethink. Phase 1.2 shipped a hybrid pain-fix; Phase 2.1 is the full redesign with prototype routes.
- **Image-card export technique** — Phase 2.3 needs an owner pick between `html2canvas` client-side and a server-side Playwright render.

### Surfaced by migration audit (2026-05-17)

These came out of the step-5 audit of the current codebase. They're not bugs to fix this session — they're decisions or design conversations to have before the relevant phase.

- **Schema migrations are unversioned and run every boot.** `db/seed.py:apply_migrations()` uses `PRAGMA table_info` guards. Works at current scale; will hurt if a Phase 2 migration is expensive (e.g. FTS5 indexing all poems). Decide: introduce a version table / alembic / nothing-yet — before Phase 2 starts.
- **Dual submission backends.** ~~Should consolidate before Phase 1.8.~~ **Resolved 2026-05-17:** legacy JSON path scheduled for removal — see backlog entry "Remove legacy JSON submission backend." SQLite becomes the only submission path.
- **View-mode resolution runs client-side.** The plain/pasture fallback chain (server pref → localStorage → `prefers-reduced-motion` → pasture) is implemented in JS on the permalink page. If JS is disabled or breaks, accessibility-driven fallback doesn't run. Server should compute the effective mode and emit it directly. Decide before next renderer touch (probably Phase 1.7 or 1.8).
- **Datamuse API has no graceful degradation.** `poetry.py` fetches rhymes/synonyms over the network with an in-memory cache only; on outage or rate-limit the user sees "no results" silently. Decide: stale-cache fallback, explicit "API unavailable" UX, or feature-flag-disable behavior.
- **Clerk role and PIN admin are independent auth systems.** ~~Decide before any "co-maintainer" scenario.~~ **Resolved 2026-05-17:** PIN scheduled for removal — see backlog entry "Remove PIN admin auth." Open follow-up: admin-promotion UI so Clerk users can be elevated without DB surgery.
- **No automated test suite exists.** Verification is manual + production smoke. Each shipped phase increases the regression surface. Decide when the cost/benefit flips — probably tied to either "first co-maintainer joins" or "Phase 2 starts touching renderer in non-obvious ways."
- **Horse dictionary: stay as `data/horses.json.gz`, or move to SQLite?** Raised by Clover 2026-05-17: *"now that we are doing an SQLite DB does the stand alone dictionary make sense or would there be potential upsides to moving the horses to a big kid database instead of a gzipped blob?"* The archived decision (stays a file) was made before SQLite entered the stack for poems; legitimate to revisit now.
  - **Stay-as-file upsides:** O(1) lookups via `word_index`; fast, working, well-understood. Easy to ship updates (replace the gz). Simple to reason about. matcher.py is built around it.
  - **Move-to-SQLite upsides:** ~30MB RAM × 2 gunicorn workers freed up; queryable on registry/country/birth_year (powers the 1.8 "contains horse" autocomplete and per-horse pages from 2.10 more naturally); FTS5 for fuzzy name search lands cleanly; overrides become tracked rows instead of an overlay JSON; dictionary updates can be incremental instead of SFTP-and-restart; the next-feature surface (per-horse stats from 2.12, on-demand PQ scrape cache from 2.7) wants something queryable anyway.
  - **Costs:** non-trivial surgery in `matcher.py` and the dictionary loading path; per-lookup DB overhead vs in-memory dict access (matcher does many lookups per submitted poem); harder dictionary-version rollback (was "swap a file"); needs a decision about whether the gz becomes the source-of-truth that gets re-imported, or the SQLite table becomes canonical.
  - **Decide:** before Phase 2.7 (on-demand PQ scrape with cache) or Phase 2.10 (per-horse browse pages) — whichever lands first — because both want queryable dictionary surface. Doesn't block 1.7–1.21.
  - **Clover's current lean (2026-05-17):** *"If it ain't broke let's leave it until we have a real need for the full DB."* Stay-as-file until a feature genuinely forces the question. Worth keeping in mind as new metadata features are added — if we keep accreting overlay JSON files alongside the gz, that's a signal the question is closer to live.
  - **Hybrid worth considering when the time comes:** dictionary for the hot matcher.py lookup path (stays O(1), low surgery), SQLite for query-heavy surfaces (browse filters, per-horse stats pages, override tracking with history). The two synced at app boot or via a build step. Note: `data/horse_overrides.json` is already a small overlay-on-the-gz, so the architecture is informally already hybrid; the open question is whether to formalize and grow that layer in SQLite.

### Bugs (small, drop into next available PR)

- ~~**`poems.lines_json` schema comment is outdated.**~~ Fixed 2026-05-22.
- **Admin PIN logout has no UI affordance.** Deliberately deferred — PIN auth is scheduled for full removal; no point adding a link for a deprecated path.
- ~~**Same-name horses all render with the first horse's URL.**~~ Fixed 2026-05-22 — render-time URL cycling.

---

## Decisions log

Pre-migration architecture and product calls. Each is labeled per the vocabulary in CLAUDE-REFERENCE.md. Most are tagged `[pre-migration — provenance unknown]` because they predate the new decision-tracking workflow; that label is honest about where the workflow started, not a judgment on the decisions themselves.

### Architecture · settled

- Domain `poet.horse` (only one for MVP) · `[pre-migration — provenance unknown]`
- Hosting on Jon's radio-station VPS (`zap.rupture.net`); independent VPS only if traffic warrants · `[pre-migration — provenance unknown]`
- Deploy: GitHub → VPS via GitHub Actions (1.23 ✅); `appleboy/ssh-action`, DEPLOY_SSH_KEY secret, full uv path · `[pre-migration — provenance unknown]`
- Stack: Flask + Jinja + vanilla JS (no SPA) · `[pre-migration — provenance unknown]`
- Datastore: SQLite (single file, FTS5 for poem search) for poems/users/tags/submissions · `[pre-migration — provenance unknown]`
- Horse dictionary: static `data/horses.json.gz` (~30 MB) loaded at app start; not in SQLite (lookups O(1) via `word_index`, SQLite would add overhead) · `[pre-migration — provenance unknown]`
- Auth: Clerk (Google live; other providers pending OAuth setup); free tier ≤10k MAU · `[pre-migration — provenance unknown]`
- Anonymous flow: full tool access pre-login; localStorage for stable/drafts/prefs; anonymous poems permanently anonymous · `[pre-migration — provenance unknown]`
- Poem IDs: UUID4 hex internal; 11-char base62 short code (`secrets.token_urlsafe(8)`, sanitized) for public URL `/p/<short>` · `[pre-migration — provenance unknown]`
- Tag taxonomy: curated categories + admin-approved suggestions; MVP categories are Poem Type, Theme, Linguistic Features, Content Warnings · `[pre-migration — provenance unknown]`
- Cross-posting: admin-flagged → queue → scheduled bots per platform. Same schedule fine for MVP; schema supports per-platform schedules · `[pre-migration — provenance unknown]`
- API: internal-only at launch; public exposure deferred to Phase 3 · `[pre-migration — provenance unknown]`
- Editor UI: utilitarian + accessible (no body-part whimsy on editor chips); coat color + famous shimmer only. Phase 2.1 is the full rethink · `[pre-migration — provenance unknown]`
- Display UI: two render paths — plain (default for accessibility / reduced-motion / explicit pref) and pasture (full decoration, default for permalinks) · `[pre-migration — provenance unknown]`
- Favorites: Pasture (working storage, explicit add) and Save (blue-ribbon sentiment) are distinct per-user collections; both private; aggregates feed admin curation and popularity rankings only · `[pre-migration — provenance unknown]`
- Print: two `@media print` stylesheets — plain (also `.txt` source) and Victorian broadsheet (also fancy image-card source) · `[pre-migration — provenance unknown]`

### Cross-cutting commitments

These bind every phase. Pulled forward from the pre-migration ROADMAP because they're load-bearing for future work.

- **Accessibility-first.** Keyboard-reachable, alt-tagged, `prefers-reduced-motion`-respecting.
- **No tracking.** No analytics SDKs, no third-party pixels, no fingerprinting. Self-hosted Plausible acceptable later if needed.
- **Plain-mode parity.** Every feature must work in plain (reader) mode. If a feature only exists in pasture mode, that's a flag to redesign it.
- **The dictionary stays a fact, not a vibe.** Don't filter horses by name appropriateness — moderation happens on poems, not the source data.
- **Admin work is rare and explicit.** Don't automate it; don't hide it behind heuristics. Curation is the product.
- **Web 1.0 ethos.** Static where possible, light JS, view-source-able.
- **No upvotes, no addictive engagement loops.** No thumbs-up affordance, no notification nudges toward more engagement, no leaderboard on the front page. Popularity *signals* (saves, ribbon counts, pasture-adds) may surface in deliberate, opt-in discovery contexts — e.g. "most saved poem about love" as a search filter, "most-ribbon-tagged horse" as a fun glimmer — but **never as the dominant frame of the site.** Rule from the 2026-05-17 product-spec interview: *"mechanical web-2 elements can exist in deliberate, opt-in discovery surfaces; they cannot become the dominant frame."* This supersedes the flat-no on surfacing in the archived ROADMAP.
- **UI vs display separation.** Functional UI utilitarian (color + grass only); whimsy lives in display surfaces or opt-in modes.
- **Tumblr is one connector among many.** Website is canonical; Tumblr work never on the critical path.

### Product · default calls flagged as overridable

- Counting feature kept at `poet.horse/count` with no redesign; Tumblr posting from there still works for admins · `[pre-migration — provenance unknown]`
- Multi-format line breaks deferred; MVP encodes only `newline` breaks with a publish-time warning on empty lines (intentional vs strip) · `[pre-migration — provenance unknown]`
- Old-poem import from `data/poems/*.json` and counting-horses Tumblr is best-effort one-shot; fresh start acceptable if conversion is messy · `[pre-migration — provenance unknown]`
- Pre-1.2 strip-decoration decision **reversed post-ship** — decorated chips are the canonical default, plain is accessibility opt-in. Shipped reskin lives in Phase 1.6; final styling pass is pre-beta · `[pre-migration — provenance unknown]`
- Attribution ("After / Translation") is a per-poem flag (`inspired_by_text` + `inspired_by_url`), **not** a tag. Briefly seeded as a tag in 1.3, then pulled · `[pre-migration — provenance unknown]`

### Pre-beta operating posture

- **Pre-beta: break freely (2026-05-19)** · `[Clover, explicit]` — until beta, Clover is the only user. Preferences can be erased, features can change, things can break. No one gets hurt and we fix it while laughing. Beta is the threshold where actual users arrive and normal care applies. Until then: move fast, don't over-engineer for stability, don't add migration shims or backwards-compat scaffolding just to protect data that doesn't exist yet.

### Migration session

- **Migration to claude-project-template adopted (2026-05-17)** · `[Clover proposed, Claude approved]` — running this session under MIGRATION.md. Confirmed: working in this worktree (PR up), deriving ROADMAP from CLAUDE.md structure, phase block reads "Migration" until step 8, Opus · high.
- **Metrics surfacing refined (2026-05-17)** · `[Clover proposed, migration session — supersedes archived commitment]` — the archived cross-cutting commitment said public engagement metrics were never surfaced. Refined position: surface in deliberate, opt-in discovery contexts; never as the dominant frame. See updated commitment above. Triggered by Q5 of the product-spec interview.
- **Ads / tracking distinction clarified (2026-05-17)** · `[pre-migration — provenance unknown, surfaced this session]` — the archived Phase 4.2 already permits polite Carbon-style banner ads; the cross-cutting "no tracking" rule applies to pixels / SDKs / fingerprinting, not to ads themselves. Default user-facing policy: "we may run ads but you can block them if you want, we don't go out of our way to hoover up your data but we are not the place to expect real privacy shields." Not new — formalizing what was implicit.
- **AI submissions out of scope (2026-05-17)** · `[Clover proposed, Claude approved]` — stated rule: "AI get the same restriction as under 13s — if you can successfully pretend to be an adult human there's nothing I can do to stop you but please behave and post good poems." The horse-name constraint does most of the enforcement work. Site does not attempt detection; rule is stated and the constraint is the filter.
- **No DMs, no comment sections (2026-05-17)** · `[Clover proposed, Claude approved]` — connection happens off-platform via profile external links. Reply-via-your-own-poem is the engagement model.
- **bs4 intentionally NOT in `requirements.txt`** · `[Clover proposed, Claude approved]` — used by `post_builder.py` (Tumblr NPF parsing) and `scraper.py`. VPS has bs4 installed out-of-band; local dev `.venv-local` has it via manual install. Rationale: "bs4 is used for scraping and database parsing, not a concern for what we are doing now and doesn't need to be in the dev deploy package." Do not "fix" by adding to requirements.txt as a fly-by cleanup. Revisit only if a feature outside scraper/Tumblr-NPF needs it.
- **Poem visibility via short-code obscurity** · `[pre-migration — provenance unknown]` — drafts at `/p/<short_code>` are accessible to anyone with the URL. Short code is ~64 bits of entropy. Explicit MVP choice: privacy-through-obscurity, not access control. Revisit before any feature that auto-shares draft URLs.
- **Tumblr OAuth tokens stored unencrypted on disk** · `[pre-migration — provenance unknown]` — `tumblr_tokens.json` plain JSON. Acceptable for hobby-tier risk; revisit if site scope grows or VPS environment changes.
- **Draft TTL: 1 hour, silent expiry** · `[pre-migration — provenance unknown]` — drafts in `queue_handler.py` expire after 3600s with no UI warning or auto-save fallback. Known UX gap; auto-save to localStorage planned but unspecced.
- **Legacy utility files remain in repo root** · `[pre-migration — provenance unknown]` — `scraper.py`, `build_db.py`, `build_famous.py`, `fix_single_letters.py`, `validate_links.py`, `prototypes/`, `tumblr-theme.html`, `poem_store.py` (dead, pre-SQLite). Not imported by the app. Move to `scripts/legacy/` (or delete `poem_store.py` outright) in a separate cleanup PR.
- **Dictionary load failure is silent** · `[pre-migration — provenance unknown]` — `matcher.py:57` falls back through rich → legacy → error-to-stdout, then continues with `dictionary.loaded = False`. Routes still work but search returns nothing. Add a startup health check / louder log before Phase 2.
