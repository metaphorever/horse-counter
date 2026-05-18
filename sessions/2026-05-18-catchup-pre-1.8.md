# Session: Catchup + Pre-1.8 housekeeping

```
Model:                Sonnet 4.6
Effort:               medium
Uncertainty flagging: standard
Git:                  branch claude/vigilant-snyder-339a18
Open holds:           none at open — docs out of sync with git
```

## What we did

**Doc catchup** — CLAUDE.md and ROADMAP.md were both stale from 1.6.1 and 1.7 shipping without session logs. Root cause: "one more thing" additions after the close checklist should have run. Fixed this session:
- ROADMAP.md: cleared active blockers, moved 1.6.1 + 1.7 to Shipped, noted /browse stub for 1.8
- CLAUDE.md: current phase advanced to 1.8; hard-stop rule added to close checklist
- Catch-up session logs written for 1.6.1 and 1.7 from commit evidence

**Tag taxonomy dedup fix** — Clover noticed duplicate tags and the entire Content Warnings category were duplicated in production. Root cause: `tag_categories` and `tags` tables created from an older `schema.sql` before the `UNIQUE` constraint on `slug` existed; `INSERT OR IGNORE` in `seed_tag_taxonomy()` had no constraint to trigger on, so every boot inserted fresh taxonomy rows. Fix: `dedup_tag_taxonomy()` added to `db/seed.py`, runs before seeding on every boot. Collapses duplicate category/tag rows (keeping lowest id, reparenting `tags.category_id` and `poem_tags.tag_id`), then creates named UNIQUE indexes so the constraint is enforced regardless of table origin.

**1.8 scoping conversation** — Featured, Browse, Random discussed. Decisions:
- Featured: separate admin curation layer (new tables, not the existing tag taxonomy). Multiple tags can be active simultaneously.
- Browse: pagination + sort by date/horse-count + filter by tag. FTS5 and per-horse/per-tag landing pages deferred to Phase 2.
- Random: redirect to a random published poem.

## Decisions

- `[confirmed]` Hard-stop rule: once session close checklist step 3 begins, no new code. Any "one more thing" goes to ROADMAP and the next session.
- `[confirmed]` Tag dedup fix: runs before seed on every boot; idempotent; adds UNIQUE indexes. Production state repaired on next restart.
- `[confirmed]` 1.8 Browse scope: pagination + sort + tag filter. No FTS5.
- `[confirmed]` 1.8 Featured: multiple active curation slots allowed simultaneously.

## Testing holds

- **After next VPS restart:** confirm tag/category duplication is gone. If duplicates persist after restart, the production DB constraint situation is different than diagnosed — flag and investigate before 1.8 tag-filter work touches the taxonomy.

## Next session

**Phase 1.8 — Featured / Browse / Random · Sonnet · high**

Holds to clear: VPS restart + tag dedup verification before starting.
