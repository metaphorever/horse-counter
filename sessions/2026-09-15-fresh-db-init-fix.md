# Session — 2026-09-15 — Out-of-band fix: a brand-new database crashed at boot

## Session setup
- Model / Effort / Uncertainty: Opus 5 · effort as set in the app, not re-confirmed · standard
- Git: `claude/bold-shaw-49f068`, level with `origin/master` at `e494228`
- Open holds at open: the Phase 2.5.1 design sprint (next is still Claude pass 2 + posing/bake · Opus · high). This session doesn't touch it.
- Out of phase on purpose. Clover brought a bugfix with the diagnosis already done. It's mechanical and small, so it's one PR.

## The ask
`init_db()` applies `schema.sql`, then `seed.run_all()`. `run_all()` ran `apply_migrations()` first, and that ALTERs `crosspost_queue` to add the Phase 2.2 status columns. But `crosspost_queue` isn't in `schema.sql`: it's created by `ensure_crosspost_queue()`, which ran last. On any new DB, init failed with `sqlite3.OperationalError: no such table: crosspost_queue`. `app.py` calls `init_db()` at import, so the app couldn't start. The documented `python -m tools.init_db` fails the same way. Production was fine because its table already existed.

## What shipped
1. **`db/seed.py` `run_all()`:** `ensure_crosspost_queue()` now runs first, before `apply_migrations()`. It's `CREATE TABLE IF NOT EXISTS`, so production sees no change.
2. **The rule is written where people will look.** The `_COLUMN_MIGRATIONS` header says every table in the list must already exist. `ensure_crosspost_queue()`'s docstring says the status columns come from the migrations.
3. **`spec/technical.md` Data model:** one sentence on the ordering rule and why.
4. **`ROADMAP.md` Bugs:** this fix, logged as done, plus a new open entry for the `--seed-tags` problem below.

## Verified (locally)
- **Repro before the fix:** a fresh DB crashed exactly as reported, at `seed.py:141`.
- **After the fix, on a fresh DB:**
  - Run 1 completes. `crosspost_queue` = `id, poem_id, status, queued_at, posted_at, tumblr_status, bluesky_status`. 18 tables, 41 tags, 4 categories, 1 admin setting.
  - Run 2 is a no-op: identical shape and counts.
  - **Pre-2.2 shape:** I dropped both status columns by hand and re-ran init. The migrations added them back, which is production's original upgrade path.
  - **`import app` on a fresh DB** (the real crash path): completes. Its only error is a missing horse dictionary, which is expected because the gz isn't in a worktree.
  - `python -m tools.init_db --seed-tags` completes, but see the ROADMAP entry.
  - Re-ran the fresh-DB double run once more on the final code.
- **No real DB was touched.** This worktree's `data/` had no `poet.db`. `BASE_DIR` resolves to the worktree, so Clover's main-checkout DB was never in reach. Every test DB was moved to the session scratchpad afterwards, not left in `data/`.

## Decisions made
- **Create the table before migrating (reorder):** Clover proposed, Claude approved.
- **The CREATE stays without the status columns.** The migrations are the only place those columns are defined, for fresh and old DBs alike, and after the reorder a fresh DB ends up exactly like production. Adding them to the CREATE as well would work, but it would define them twice. This was Claude's call, and a low-stakes one.
- **No "skip tables that don't exist" guard in `apply_migrations()`.** Clover floated it as optional. Claude pushed back, and it's **awaiting Clover's call.** Concern: a silent skip trades a loud boot crash for a quiet schema gap. If the ordering trap came back, a missing table's migrations would be skipped. Its `ensure_*()` would then create it *without* those columns, and the app would fail at query time with `no such column` until the next restart re-ran the migrations. The crash we just fixed was loud, caught before production, and pointed straight at the cause. Instead, the rule is written next to `_COLUMN_MIGRATIONS`, where the next migration gets added. If Clover wants a guard anyway, the better version raises a clear error naming the ordering rule rather than skipping.

## Uncertainty flags
- **Uncertain:** whether production ever had `--seed-tags` run, and so carries the legacy duplicate taxonomy · resolve with the read-only query in the ROADMAP entry. Out of scope here.

## Testing holds
Production's `crosspost_queue` already exists, so the reorder is a no-op there. The hold is a smoke check that boot still works after the auto-deploy.
- "After the deploy, did poet.horse load normally? Did the admin crosspost queue page open, and show its usual items?"

## Carryover
- Phase 2.5.1 is unchanged. Next session: Claude pass 2 + posing/bake · Opus · high.
- A task chip is pending for the `--seed-tags` legacy taxonomy (details in ROADMAP Bugs).

## Deferred / added to roadmap
- **`--seed-tags` writes a second, legacy tag taxonomy** → ROADMAP Bugs, plus a task chip. `tools/seed_tags.py` dates from Phase 0.2. Its slugs don't collide with `seed.py`'s namespaced ones, so on a fresh DB it added 35 duplicate-ish tags and a singular `content-warning` category. Deploy doesn't run it, but both docs give it as the migrate command.
- **Deferred:** `crosspost_queue` is the one table created in `seed.py` instead of `schema.sql`. Consolidating it there would remove this class of trap. The natural time is the Mastodon trigger, when the status columns graduate to a `crosspost_targets` child table (ROADMAP 2.2 note). No separate entry.
