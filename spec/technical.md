# poet.horse — Technical spec

State of the codebase as it actually exists at migration time (commit `ebed39e`, Phase 1.6 shipped). This is the **as-built** doc — what's true today, not what's aspirational. Aspirational work lives in `ROADMAP.md`.

For deployment, ops, and prod environment specifics, see `DEPLOYMENT.md` at repo root. This spec references it but doesn't duplicate it.

---

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Web server | Apache 2.4 (Jon's VPS) | reverse-proxy → gunicorn at `127.0.0.1:8765` |
| App server | gunicorn (2 workers) | systemd user service `poet-horse.service` |
| Framework | Flask 3.x + Jinja2 | no SPA, no async — view-source-able by design |
| Database | SQLite (`data/poet.db`) | WAL mode, foreign keys on, FTS5 planned for Phase 2.11 |
| Dictionary | static `data/horses.json.gz` (~30 MB) | loaded once at app startup; in-memory |
| Auth | Clerk (live tier) | JWT verification via JWKS; admin PIN fallback |
| Frontend | Vanilla JS, per-page `<script>` blocks | no bundler, no framework |
| Deploy | Manual `git pull` + `systemctl --user restart` | GitHub Actions deploy planned (Phase 1.23) |

No ORM. No task queue. No Redis. No tracker. No SPA framework. This is deliberate (Web 1.0 ethos, see `spec/product.md`).

---

## Request flow

1. Browser → `https://poet.horse` → Cloudflare (orange-proxied)
2. Cloudflare → Apache vhost on `162.221.25.24:443`
3. Apache reverse-proxy → gunicorn on `127.0.0.1:8765`
4. gunicorn → Flask app (`app.py:create_app` pattern is implicit — module-level app)
5. `@app.before_request` → `load_current_user()` populates `g.current_user` from Flask session
6. Route handler → optionally checks `_is_admin()` / `@user_required` / `@login_required`
7. Response rendered via Jinja template; static assets served by Flask in dev, Apache in prod (TBD — currently Flask serves)

Clerk satellite CNAMEs (5 total) are grey-proxied at Cloudflare because Clerk breaks otherwise. Clerk JS loads from `clerk.poet.horse` proxy (the generic jsdelivr URL is the headless build and `mountSignIn` fails on it).

---

## Data model

Schema lives in `db/schema.sql`; migrations applied idempotently by `db/seed.py:apply_migrations()` on every `init_db` run (called at startup). No versioned migration table — adds are guarded by `PRAGMA table_info` checks. This works for the current scale; will need to evolve before Phase 2 if migrations become expensive (flagged as an open design question).

### Tables

| Table | Purpose | Key shape notes |
|---|---|---|
| `users` | Account records | `clerk_id UNIQUE`, `slug UNIQUE`, `role ('user'\|'admin')`, `trust_level ('pending'\|'trusted'\|'flagged')`, JSON columns for `preferences_json` / `flags_json` / `links_json` |
| `poems` | Poem records | `short_code UNIQUE` (11-char base62), `lines_json` blob, `status ('draft'\|'submitted'\|'published'\|'hidden'\|'rejected')`, dual authorship: `author_user_id` (FK) OR `author_display_name + author_link_url` for anonymous, denormalized `horse_count` / `word_count`, `inspired_by_text + inspired_by_url` flag pair |
| `tag_categories` | Tag taxonomy categories | `behavior ('single_select'\|'multi_select'\|'content_warning')` |
| `tags` | Tag definitions | `status ('active'\|'pending'\|'rejected')` — user-suggested land as `pending` |
| `poem_tags` | M:N poem ↔ tag | per-application `status` (approve a tag application without approving the tag itself) |
| `submissions` | Poem submission queue | 1:1 with poems, `status`, admin reviewer FK |
| `reports` | User-submitted reports | `target_type ('poem'\|'display_name'\|'slug'\|'tag')`, `reporter_ip` for anon rate-limiting |
| `drafts` | Server-side drafts (logged-in users) | `ON DELETE CASCADE` from users |
| `stable_horses` | Per-user working pool for poem composition | name-keyed, `remaining` count 1-99 |
| `pasture_horses` | Per-user long-term collection (distinct from stable) | name-keyed |

### JSON shapes

- **`users.preferences_json`** — `{"poem_name": str, "poem_tumblr": str, "page_size": str, "poem_view_mode": "plain"|"pasture", ...}`. Keys are **allow-listed** in `_USER_PREF_WRITES` at `app.py:406` — server validates each key on write. Never a free-form k/v store.
- **`users.flags_json`** — `{"ad_free": bool, ...}`
- **`users.links_json`** — `[{"label": str, "url": str}, ...]` — used for profile external links (planned Phase 1.15)
- **`poems.lines_json`** — runtime shape: `[[{"name": str, "display": str, "url": str, "coat": str, "rev": str, "is_famous": bool}, ...], ...]` (list of lines; each line is a list of horse dicts). The schema.sql comment describes a different shape (`[{"horses": [...], "break": "newline"}]`) — that comment is **outdated**; the code passes the raw JSON through without re-serialization, so the discrepancy is invisible at runtime but misleading on read. Flagged in `ROADMAP.md` open design questions.

### Dictionary (not in SQLite)

- File: `data/horses.json.gz` (~30 MB; SFTP'd to VPS on fresh deploy, in `.gitignore`)
- Loaded once at `app.py:101` into `matcher.HorseDictionary`
- Structure: `{"word_index": {first_word: [normalized_name, ...]}, "horses": {normalized_name: [{id, display_name, registry, country, birth_year, url}, ...]}}`
- Overrides layer: `data/horse_overrides.json` (admin-edited in production, applied at load time — see `ROADMAP.md` backlog: "Sync `data/horse_overrides.json` from production back to git")
- Fallback to legacy `horses_compressed.json.gz` if rich format missing — silent fallback, no UX signal. Flagged in open design questions.

---

## Routes

Full catalog in the codebase; here's the grouping. See `app.py` for one-line per route.

- **Counter (legacy)**: `/`, `/queue` — original horse-counter flow, kept under `/count` IA per ROADMAP cross-cutting commitment.
- **Poetry editor**: `/poetry`, `/poetry/search`, `/poetry/random`, `/poetry/short`, `/poetry/rhyme/{terms,horses}`, `/poetry/thesaurus/{terms,horses}`, `/poetry/stable/{add,remove,clear}`
- **Submissions**: `/submit` (legacy URL/text), `/submit/poem` (poem), `/tags/suggest`
- **Auth**: `/sign-in`, `/auth/clerk/verify`, `/sign-out`, `/setup-account`, `/login`, `/logout` (PIN fallback)
- **Tumblr OAuth**: `/auth`, `/callback` (admin only)
- **User account**: `/me/sync`, `/me/preferences`, `/me/pasture/add`, `/me/{published,drafts,pasture,saved-poems,saved-horses,profile}` (most are coming-soon stubs awaiting Phase 1.15 / 1.19)
- **Public profiles**: `/u/<slug>` (stub; Phase 1.15)
- **Permalink renderer**: `/p/<short_code>` — published poems public, drafts visible to author/admin only via short-code obscurity (see decision below)
- **Legal**: `/terms`, `/privacy`, `/data-deletion`
- **Coming-soon stubs**: `/featured`, `/browse`, `/random`, `/pasture` (each phase ships one)
- **Admin**: `/submissions` (legacy queue), `/admin/poem-queue` (new queue), `/admin/dictionary` (search + overrides)

---

## Dependencies

`requirements.txt`:

```
Flask>=3.0,<4
gunicorn>=21,<23
requests>=2.31,<3
PyJWT>=2.8,<3
cryptography>=42,<45
```

- **Flask** — web framework
- **gunicorn** — production WSGI server (dev runs Flask's built-in server)
- **requests** — Tumblr API, Clerk JWKS fetch, Datamuse rhyme/thesaurus
- **PyJWT** — Clerk session JWT verification (RS256)
- **cryptography** — transitive for PyJWT RSA handling, pinned explicitly to lock the version range

**Explicit decision: `beautifulsoup4` is NOT in `requirements.txt`.** Used by `post_builder.py` (Tumblr NPF parsing) and `scraper.py` (PQ scraping). Per Clover, "bs4 is used for scraping and database parsing, not a concern for what we are doing now and doesn't need to be in the dev deploy package." The runtime VPS has bs4 installed out-of-band; local dev `.venv-local` has it via manual install for scraping scripts. **Do not "fix" this by adding to requirements.txt** — it's an intentional exclusion. If a future feature genuinely needs bs4 outside the scraper / Tumblr-NPF code paths, revisit then. Recorded in `ROADMAP.md` decisions log.

No other unpinned imports. No transitive deps brought in for convenience.

---

## Build / run / test / deploy commands

These get inherited into `CLAUDE-REFERENCE.md`'s build-commands block.

### Local development

```bash
# Install deps (user prefers `uv pip`)
uv pip install -r requirements.txt

# Or standard:
pip install -r requirements.txt

# Initialize / migrate the database (idempotent)
python -m tools.init_db --seed-tags

# Run dev server
python app.py
# → http://localhost:5000
```

`uv pip` is the preferred install pattern — see memory entry. On the VPS, pip isn't available; the activate sequence is required.

### Tests

**There is no test suite.** No `tests/` directory, no pytest config, no CI. Verification is manual + production smoke.

This is acknowledged. Phase 1.7+ work continues to ship without automated tests; the cost/benefit is being deferred. Worth a real design conversation before Phase 2 — flagged in `ROADMAP.md` open design questions.

### Production deploy

Manual until Phase 1.23 ships GitHub Actions:

```bash
# On the VPS (zap.rupture.net):
cd /data/home/metaphorever/horse-counter
git pull origin master
/home/metaphorever/.venv/bin/uv pip install -r requirements.txt   # only if deps changed
systemctl --user restart poet-horse.service
```

Health check:

```bash
systemctl --user status poet-horse.service
curl -vk https://162.221.25.24/                 # origin reachable?
curl -v https://poet.horse/                     # full stack via Cloudflare?
```

DB admin happens via Python one-liners (no `sqlite3` CLI on the VPS). Patterns in `DEPLOYMENT.md`.

---

## Git workflow

**Branch model:** `master` is the active production branch. Feature work happens in `claude/<name>` worktrees under `.claude/worktrees/`, one per PR.

**PR cadence:** one PR per ROADMAP task (see feedback memory). Squash-merge into master with the PR number in the commit message (`Phase 1.6 — two-mode renderer (plain / pasture) (#20)`). The squash creates a single commit on master with no parent link to the feature branch, which is why post-merge branch cleanup is required (the GitHub UI flags squash-merged branches as un-merged).

**Stacked PRs:** the 1.3 / 1.5 / 1.6 series were stacked on top of each other while in review. Lesson learned (from feedback memory): **do not use `--delete-branch` when merging stacked PRs** — deleting the base branch auto-closes the children. Merge bottom-up bare; clean up branches after.

**No pre-commit hooks. No CI.** Both planned (1.23 deploy workflow; testing strategy TBD).

**`vps-rebuild` branch is stale** but intentionally kept around for now (pre-cutover artifact).

---

## Frontend organization

- Single base template: `templates/base.html` — nav, footer, Clerk JS, context-processor-injected globals
- All other templates extend base
- Per-page JS lives inline in `<script>` blocks within each template. No module bundler.
- `static/style.css` (single stylesheet), `static/grass.svg` (background tile), `static/img/` (assets)
- Coat-color palette: CSS variables on `:root` in `style.css`, shared between editor and pasture-mode renderer (added Phase 1.6 to avoid hex copy-paste)
- localStorage usage: anonymous user state (`horse-stable`, `horse-poem-name`, `horse-poem-tumblr`, `horse-page-size`, `poem-view-mode`)
- `prefers-reduced-motion` and `prefers-contrast` respected via CSS media queries; view-mode resolution chain reads it on the client (flagged — should be server-side; see open design questions)

---

## Out-of-band decisions / known gaps

These are decisions or omissions made in code without being formally documented before this migration. Most go into the `ROADMAP.md` decisions log; a few become **Open design questions** for future resolution.

| Item | Where | Resolution |
|---|---|---|
| bs4 deliberately out of `requirements.txt` | post_builder.py, scraper.py | Documented above; decisions log |
| Schema migrations are unversioned, run every boot | db/seed.py | Open design question — revisit before Phase 2 |
| Poem visibility via short-code obscurity (not perms) | app.py:1407 | Decisions log — explicit MVP choice |
| Dual submission backends: legacy JSON + new SQLite | submissions.py, poem_submissions.py | Open design question — consolidate before 1.8 |
| View-mode fallback chain runs client-side | poem.html JS | Open design question — server should be authoritative for accessibility |
| Datamuse calls have no graceful degradation | poetry.py | Open design question — handle API outage + rate limiting |
| `poems.lines_json` schema comment is outdated vs code | db/schema.sql:36 | Bug — fix the comment in a follow-up |
| Clerk role and PIN admin are independent | app.py:122 (`_is_admin`) | Open design question — needs role-management UI for self-serve admin |
| Admin PIN logout has no UI affordance | app.py:230 | Bug — add logout link to admin nav |
| Tumblr OAuth tokens stored unencrypted on disk | auth.py:56 | Decisions log — acceptable for hobby-tier risk; revisit if scope grows |
| Draft TTL silently expires after 1 hour | queue_handler.py:33 | Decisions log — known UX; auto-save planned but unspecced |
| Dictionary load failure is silent | matcher.py:57 | Decisions log — add startup health check before Phase 2 |
| Legacy utility files still in repo root | scraper.py, build_db.py, etc. | Decisions log — move to `scripts/` directory in a separate cleanup PR |
| `poem_store.py` is dead code (pre-SQLite layer) | poem_store.py | Decisions log — delete in cleanup PR |
| No test suite exists | (absence) | Open design question — when does automated testing become worth the cost? |

These are catalogued in more detail in `ROADMAP.md`. They're not addressed in this migration session — surfacing them is the deliverable.
