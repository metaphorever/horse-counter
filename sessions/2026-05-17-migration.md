# Session — 2026-05-17 — Migration: poet.horse

## Session setup

- **Model / Effort / Uncertainty:** Opus 4.7 · high · standard
- **Open holds:** none (migration session)
- **Git:** worktree `claude/thirsty-austin-afe580`, off `master` at `ebed39e`

---

## What shipped

- Installed `CLAUDE.md` (current-phase block set to "Migration") and `CLAUDE-REFERENCE.md` (with build-commands block added per migration step 4 instruction).
- Derived new `ROADMAP.md` from the template structure: phase map (Phase 0 closed; Phase 1 mid-flight through 1.6), backlog, open design questions, decisions log.
- Created `sessions/` and `spec/` directories.
- Archived old `ROADMAP.md` (583 lines) and old `TODO.md` (46 lines) into `sessions/pre-migration-history.md` with the prescribed header.
- Wrote `spec/product.md` from a 5-question interview with Clover. Voice preserved throughout (direct quotes).
- Wrote `spec/technical.md` from a codebase audit: stack, request flow, data model with JSON shapes, routes catalog, deps, build/run/deploy commands, git workflow, out-of-band decisions table.
- Folded audit findings into `ROADMAP.md` under "Open design questions" (6 items) and "Decisions log" (6 new entries).
- Pre-migration ancillary cleanup: main repo switched from stale `vps-rebuild` back to `master`; nine zombie local branches and three dead worktrees removed; one empty leftover dir (`affectionate-sinoussi-e901e5`) couldn't be deleted due to a file handle held by another process — git already unregistered it.

---

## Decisions made

Labels per the vocabulary in `CLAUDE-REFERENCE.md`.

- **Migration to claude-project-template adopted** · *Clover proposed, Claude approved* — running this session under `MIGRATION.md`.
- **Phase numbering: "Migration is the current phase"** · *Clover proposed, Claude approved* — old phase numbering preserved in the archived ROADMAP; current state is "Migration" until step 8 closes; next phase is 1.7 (horse popover) per the unchanged plan.
- **Metrics surfacing refined** · *Clover proposed, migration session — supersedes archived commitment* — the archived "never surfaced publicly" rule is relaxed. Popularity signals (saves, ribbon counts, pasture-adds) **may** appear in deliberate, opt-in discovery surfaces (e.g. "most saved poem about love" as a search filter, famous-horse glimmer). They **cannot** become the dominant frame of the site. Rule in one sentence: *"mechanical web-2 elements can exist in deliberate, opt-in discovery surfaces; they cannot become the dominant frame."*
- **AI-generated submissions out of scope** · *Clover proposed, Claude approved* — rule stated: *"AI get the same restriction as under 13s — if you can successfully pretend to be an adult human there's nothing I can do to stop you but please behave and post good poems."* Site does not attempt detection; the horse-name constraint does most of the enforcement work.
- **No DMs, no comment sections** · *Clover proposed, Claude approved* — connection happens off-platform via profile external links. Reply-via-your-own-poem is the engagement model.
- **bs4 deliberately NOT in `requirements.txt`** · *pre-migration — Clover explicit, formalized in this session* — used by `post_builder.py` and `scraper.py`; VPS and local dev have it installed out-of-band. Do not add to `requirements.txt` as a fly-by cleanup. Recorded in spec/technical.md and ROADMAP decisions log.
- **Importing legacy poems struck (was Phase 1.18)** · *Clover proposed, Claude approved* — *"I am thinking of doing a fresh launch rather than importing old poems to keep everything on the new site under the new explicit TOS."* Cleaner consent story. Promoted from "deferred" to "permanently out of scope" in spec/product.md.
- **Remove PIN admin auth (scheduled)** · *Clover proposed, Claude approved* — *"PIN can be pruned out whenever now that clerk is online."* Logged in ROADMAP backlog. Resolves the "Clerk role and PIN admin are independent" open design question (with a follow-up: admin-promotion UI for self-serve role elevation).
- **Remove legacy JSON submission backend (scheduled)** · *Clover proposed, Claude approved* — *"same with old json submission path."* Logged in ROADMAP backlog. Resolves the "Dual submission backends" open design question. Sequence after Phase 1.13 (admin moderation queue overhaul) which already plans the new poem-first review UI.
- **Net additions to scope from product-spec interview** · *Clover proposed, Claude approved* — follow other posters, profile bios constructed from horse names, profile external links, "response to" attribution variant. All added to ROADMAP backlog at unspecified phase.

---

## Uncertainty flags

- **Uncertain:** whether the `poems.lines_json` schema-comment discrepancy at `db/schema.sql:36` is purely a doc bug or whether some code path actually expects the documented `{"horses": [...], "break": "newline"}` shape. Read suggests it's invisible at runtime (raw passthrough) but I didn't trace every serializer. Resolves by: reading the publish-time write path in `poem_db.py` end-to-end before Phase 1.13.
- **Uncertain:** how the production VPS has `bs4` installed if it's not in `requirements.txt`. Memory says "via some other path" but didn't specify. Doesn't block anything; worth confirming during the next deploy to make sure a fresh server bootstrap would work.

---

## Testing holds

These need Clover to verify before the relevant work proceeds. Migration itself has nothing to manually test — it's docs + cleanup — but two open holds inherited:

- **Phase 1.6 (just shipped)** — verify the view-mode toggle paths end-to-end: server pref → localStorage → `prefers-reduced-motion` → pasture default. Test scenarios: signed-out + default loads pasture; signed-out + localStorage `plain` loads plain; signed-in user pref persists across sessions; reduced-motion respected. (Holds Phase 1.7 start.)
- **Migration PR deploy smoke** — once the migration PR merges to master, confirm the next production deploy still works (no `requirements.txt` changes, no code changes — should be a no-op deploy, but worth eyeballing).

---

## Carryover

What the next session needs that it can't infer from code:

- **Next phase: 1.7 — Horse popover in pasture mode** `[sonnet · high]`. Per ROADMAP. Reuses the chip-menu primitive from Phase 1.2 against the pasture-mode chips from 1.6.
- **Migration PR opens at the end of this session.** Merge that first; don't start 1.7 work until master has the new template installed.
- **One empty leftover worktree directory** at `.claude/worktrees/affectionate-sinoussi-e901e5` — can be deleted on next machine reboot. Already unregistered from git.
- **Origin/claude/\* zombie branches still exist on GitHub.** Local cleanup pruned the local copies; remotes still visible in the GitHub UI. If Clover wants the GitHub branch list tidied, that's a push-deletion step we can do separately (or in this PR's follow-up).
- **`vps-rebuild` branch kept intentionally.** Stale per memory; left alone this session.
- **Style pass session is pre-beta, not mid-feature.** Memory entry holds — when working on 1.7+ visuals, don't try to finalize styling; that's a dedicated session.

---

## Deferred / added to roadmap

Everything surfaced this session that didn't get acted on:

**Net additions to scope (in `ROADMAP.md` Backlog):**
- Follow other posters
- Profile bios made of horse names
- Profile external links
- "Response to" attribution variant
- Remove PIN admin auth
- Remove legacy JSON submission backend

**Surfaced by audit (in `ROADMAP.md` Open design questions):**
- Schema migrations are unversioned, run every boot — revisit before Phase 2
- View-mode resolution runs client-side — server should be authoritative
- Datamuse API has no graceful degradation — needs UX call
- No automated test suite — when does cost/benefit flip? Clover: *"probably a good investment when there is a logical place to add it in"*
- (Two more resolved this session — see Decisions made.)

**Bugs queued for next-available PR (in `ROADMAP.md`):**
- `db/schema.sql:36` outdated `lines_json` comment
- Admin PIN logout has no UI link (will be moot once PIN is pruned, but quick fix in the meantime)

**Decisions formalized but not new (in `ROADMAP.md` Decisions log):**
- Poem visibility via short-code obscurity
- Tumblr OAuth tokens stored unencrypted on disk
- Draft TTL: 1 hour, silent expiry
- Legacy utility files remain in repo root
- Dictionary load failure is silent
- bs4 intentionally out of requirements.txt
