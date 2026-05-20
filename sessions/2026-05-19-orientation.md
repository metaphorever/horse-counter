# Session — 2026-05-19 — Orientation / Roadmap

## Session setup

- **Model / Effort / Uncertainty:** Sonnet 4.6 · low · standard
- **Git:** worktree `claude/pensive-mendeleev-0fdd7c`, fast-forwarded from `origin/master` (0f350f8) at open
- **Open holds:** 1.11 print verification — **cleared by Clover at session open** ("everything looks good")

---

## What happened

No code shipped. Orientation after a multi-session gap + roadmap housekeeping.

### Holds cleared

- **1.11 print verification** — all nine checklist points confirmed on live site.

### Roadmap additions

- **SVG logo backlog item** — replace Smokum-typeset "poet.horse" in web nav and print masthead with `poet-horse.svg` (committed to repo root). Slot into pre-beta style pass.
- **1.12 Three-mode display system** — replaces the binary plain/pasture with: Plain (pinned note-area over decorative field, count-page box style, workhorse/admin/accessibility), Pasture (field is the surface, content floats, text separated by contrasting color outline), Reader (off-white page, print-stylesheet aesthetic on screen). Server-resolved site-wide preference. Spec session required before implementation. Text styling is prototype-first. `[opus · high]`
- **Pre-beta operating posture** — until beta Clover is the only user; preferences can be erased, features can change, things can break. Beta is the threshold for actual-user care.

### Decisions made

- **1.12 Pasture text separation** · *Clover* — contrasting color outline on text/UI elements that need to breathe against the field background. Specific color TBD at prototype stage.
- **1.12 Plain mode content areas** · *Clover* — count-page style: simple box + pin emoji, one per independent content area on a page.
- **Pre-beta data posture** · *Clover* — stored preference values (`"plain"`/`"pasture"`) can be discarded on migration; no migration shims or backwards-compat scaffolding needed before beta.

---

## Testing holds

None.

---

## Next session

**Phase 1.25 — Nav / IA polish** · Model: Sonnet · Effort: low · No holds to clear.

Scope: nav label cleanup ("Drafts", "My Poems"), remove redundant "Home", promote Featured/Browse/Random to top-level standalone items, `/` redirects to `/featured`.
