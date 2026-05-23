# Session — Status check + 1.4 close + 1.29 planning

**Date:** 2026-05-22
**Model:** Sonnet
**Effort:** medium
**Uncertainty flagging:** standard
**Git:** master (fast-forwarded from stale local — 2 commits behind at open)
**Open holds:** 1.4 testing (cleared this session)

---

## Work completed

### Status reconciliation

Local worktree was stale. After fast-forward: 1.13 and 1.4 had both shipped (PRs #48 and #50), but 1.4 was missing its session log and CLAUDE.md had not been updated. Retroactive session log written for 1.4; CLAUDE.md and ROADMAP updated and committed.

### 1.4 testing hold cleared

Clover verified all 1.4 features on poet.horse:
- Pending tag review visible ✓
- Tag rename / deactivate / safe-delete ✓
- Category rename / safe-delete ✓

### Poem rendering audit

Full audit of how poems are rendered across templates. Findings:

- **3 Jinja2 renderers** (poem.html, poem_queue.html, user_profile.html) plus 1 JS renderer (poetry.html editor)
- poem.html and poem_queue.html are near-identical; the only structural difference is `<a>` vs `<span>` per horse
- user_profile.html bio poem uses bare `horse-chip` class — missing coat/rev/famous styling entirely (bug)
- Collection pages (saved_poems, featured, my_pasture, poem_index) are title/link lists — they don't render poem bodies at all
- Turnover indent (`padding-left: 2em; text-indent: -2em`) is print-only; Clover confirmed it should apply on screen too

### Design decisions

- **confirmed** — "any list of horses is a poem": saved horses and pasture should render using the horse chip macro (coat/rev/famous styling), not bare anchor lists. Collection pages (saved poems, my poems) stay as title+metadata lists.
- **confirmed** — shared primitive is the horse chip, not the whole layout. Macro handles chip styling; layout (lines for poems, list/scattered for pasture) stays separate.
- **confirmed** — 1.29 DRY renderer is the next phase.

### Backlog additions (ROADMAP)

Five new items added:
1. Saved Horses nav button (logged-in only, next to Short Names/Random/Pasture)
2. Horses from published poems auto-added to pasture (design pivot from explicit-add-only spec)
3. Tags in Edit Details not carried to Post Poem — unify into one flow with different terminal actions
4. Suggested (new) tags not surfaced in mod queue — gap in 1.13
5. 1.29 DRY poem renderer — added as numbered phase

---

## Decisions

- **confirmed** — 1.29 before style pass. DRY renderer sets up 1.12 mode parameter cleanly.
- **noted** — pasture auto-population is a design pivot (original spec: explicit-add only). Flagged in ROADMAP.

---

## Testing holds

None. 1.29 ships no user-facing changes beyond the bio poem fix and turnover indent; standard smoke test on those two surfaces before close.

---

## Next session

**Phase 1.29 — DRY poem renderer** · Model: **Sonnet** · Effort: **medium**

Scope:
- Jinja2 macro file with `render_chip(h, mode)` and `render_poem(lines, mode)`
- Wire into poem.html, poem_queue.html, user_profile.html
- Update pasture + saved-horses routes to send coat/rev/famous data; use chip macro
- Add turnover indent to screen `.poem-line-out`

No holds to clear before starting.
