# poet.horse — Roadmap

Navigation doc for the project. Full pre-migration history lives in `sessions/pre-migration-history.md`; this file is the live map going forward.

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

**Remaining (rough order):**
- 1.7 Horse popover in pasture mode `[sonnet · high]`
- 1.8 Featured / Browse / Random `[sonnet · high]`
- 1.9 Empty-line warning at publish `[haiku · low]`
- 1.10 Export: copy as text / HTML / .txt `[sonnet · low]`
- 1.11 Plain-text print stylesheet `[sonnet · medium]`
- 1.12 Reader-mode toggle (site-wide) `[sonnet · medium]`
- 1.13 Admin moderation queue overhaul `[sonnet · high]`
- 1.14 Report button + report queue `[sonnet · medium]`
- 1.15 Poet profile `/u/<slug>` `[sonnet · medium]`
- 1.16 RSS feed `[sonnet · low]`
- 1.17 Rate limiting `[sonnet · low]`
- 1.18 One-shot import of legacy data `[sonnet · medium]`
- 1.19 Save (Blue Ribbon) + Pasture collections `[sonnet · medium]`
- 1.20 Cross-post queue (admin-flagged, Tumblr connector) `[sonnet · high]`
- 1.21 Soft sign-in prompts `[sonnet · low]`
- 1.23 GitHub Actions deploy `[sonnet · medium]`
- 1.24 DNS cutover + PA shutdown `[haiku · low — owner action]`
- 1.4 Admin tag management `[sonnet · medium]` — slot after 1.13 ships the queue
- **Style pass session** — focused styling session before beta (fancy/plain/high-contrast/typography-only print modes side-by-side; restore decorated editor chips). Pre-beta, not mid-feature.

### Phase 2 — Beta & feedback · ⏳ pending soft launch

Editor UX rethink (opus), explicit/mature display, image-card export, fancy broadsheet print, horsified HTML embed, oEmbed, per-horse PQ scrape (Cloudflare-aware), real coat colors, pasture-search mode, per-horse/per-tag browse pages, FTS5 search, site-popularity stats, ambient field horses, Bluesky/Mastodon/Threads/X connectors, Tumblr theme port, three-concept disambiguation pass.

### Phase 3 — Growth · ⏳ pending sustained traffic

Exquisite corpse mode, Hall of Fame (curated + popular), public read API + OpenAPI, horse-database public download, independent VPS migration.

### Phase 4 — Monetization · ⏳ pending revenue threshold

Ko-fi tip-jar polish, Carbon-style static ads, ad-free supporter keys, supporter cosmetic flair, lawyer review, merch/anthology exploration.

---

## Backlog

Surfaced items not yet committed to a phase. Promote to a phase when ready.

- **Tumblr post CSS desync** — new posts lose chip structural styling because Tumblr appears to strip `class` attributes; `--bg`/`--fg` inlined vars survive but `.horse-link` body-shape rules don't. Fix path: data-attribute selectors or inlined structural CSS. Deprioritized — most Tumblr viewers use dashboard (CSS stripped there anyway). Revisit after website CSS is locked. (Originally tracked in pre-migration TODO.md.)
- **Link validator** for `short-names-validation.html` and eventually the full dictionary — Cloudflare-aware Playwright session, polite rate-limit, page-content check for "not found", outputs annotated HTML or `data/link_validation.json`. Pilot with the short-names list (1362 horses). (Originally TODO.md.)
- **Sync `data/horse_overrides.json` from production back to git** — canonical overrides file lives on the server and gets edited in prod; doesn't automatically flow back. Options: one-click admin export, cron commit, or deploy-time pull-first hook. (Originally TODO.md.)
- **Ambient background horses** — a few chips in the SVG grass behind working areas (z-indexed so they never overlap UI); bonus walk-cycle. Subset of Phase 2.13. (Originally TODO.md.)
- **Follow other posters** — low-key social-graph primitive: follow a poet, see a feed of their published poems. No DMs, no friend requests, no mutual handshake. Surfaced during 2026-05-17 product-spec interview as a net addition to scope.
- **Profile bios made of horses** — required: profile bios must obey the constraint too. On-brand enforcement of the site's central rule. Pair with 1.15 (poet profiles).
- **Profile external links** — short list of links on a profile to personal sites / social platforms / contact methods. Explicit answer to "no DMs on poet.horse" — take connection off-platform. Pair with 1.15.
- **"Response to" attribution variant** — extend the Phase 1.5 attribution flag (`inspired_by_text` / `inspired_by_url`) so the URL can point at a poet.horse permalink and the UI reads as a reply rather than an external citation. Tentative — "fun and pretty low cost to build in with the current structure but it doesn't need to block anything currently in dev." Doesn't bump 1.7–1.21.

---

## Open design questions

Resolve before the relevant phase starts.

- **In-pasture horse interaction details** — popover shape confirmed (name, link, poems-featuring, add-to-pasture, ribbon-save). Exact transition / placement / dismissal behavior is a Phase 1.7 design call.
- **Editor chip interactions (one-page builder)** — drag-primary vs click-primary vs hybrid for the Phase 2 rethink. Phase 1.2 shipped a hybrid pain-fix; Phase 2.1 is the full redesign with prototype routes.
- **Image-card export technique** — Phase 2.3 needs an owner pick between `html2canvas` client-side and a server-side Playwright render.

---

## Decisions log

Pre-migration architecture and product calls. Each is labeled per the vocabulary in CLAUDE-REFERENCE.md. Most are tagged `[pre-migration — provenance unknown]` because they predate the new decision-tracking workflow; that label is honest about where the workflow started, not a judgment on the decisions themselves.

### Architecture · settled

- Domain `poet.horse` (only one for MVP) · `[pre-migration — provenance unknown]`
- Hosting on Jon's radio-station VPS (`zap.rupture.net`); independent VPS only if traffic warrants · `[pre-migration — provenance unknown]`
- Deploy: GitHub → VPS, manual `git pull` + service restart for now; GitHub Actions in 1.23 · `[pre-migration — provenance unknown]`
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

### Migration session

- **Migration to claude-project-template adopted (2026-05-17)** · `[Clover proposed, Claude approved]` — running this session under MIGRATION.md. Confirmed: working in this worktree (PR up), deriving ROADMAP from CLAUDE.md structure, phase block reads "Migration" until step 8, Opus · high.
- **Metrics surfacing refined (2026-05-17)** · `[Clover proposed, migration session — supersedes archived commitment]` — the archived cross-cutting commitment said public engagement metrics were never surfaced. Refined position: surface in deliberate, opt-in discovery contexts; never as the dominant frame. See updated commitment above. Triggered by Q5 of the product-spec interview.
- **Ads / tracking distinction clarified (2026-05-17)** · `[pre-migration — provenance unknown, surfaced this session]` — the archived Phase 4.2 already permits polite Carbon-style banner ads; the cross-cutting "no tracking" rule applies to pixels / SDKs / fingerprinting, not to ads themselves. Default user-facing policy: "we may run ads but you can block them if you want, we don't go out of our way to hoover up your data but we are not the place to expect real privacy shields." Not new — formalizing what was implicit.
- **AI submissions out of scope (2026-05-17)** · `[Clover proposed, Claude approved]` — stated rule: "AI get the same restriction as under 13s — if you can successfully pretend to be an adult human there's nothing I can do to stop you but please behave and post good poems." The horse-name constraint does most of the enforcement work. Site does not attempt detection; rule is stated and the constraint is the filter.
- **No DMs, no comment sections (2026-05-17)** · `[Clover proposed, Claude approved]` — connection happens off-platform via profile external links. Reply-via-your-own-poem is the engagement model.
