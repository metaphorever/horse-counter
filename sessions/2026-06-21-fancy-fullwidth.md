# Session — 2026-06-21 — Fancy full-width layout (post-2.4 refinement)

```
Model:                Opus 4.8
Effort:               high
Uncertainty flagging: standard
Git:                  master (direct, auto-deploy) — commits aea62a2, 2ac7c2e
Open holds at open:   none (2.4 fully verified + closed)
```

## What shipped

A UI refinement, not a numbered phase: give the big 2.4 SVG horses room to breathe
on wide screens. Two surfaces, both live + Clover-verified on poet.horse.

### Fancy poem permalink — Option C (Fancy only)
The 2.4 SVG horses only fit 3-4 per line in the old 720px column, so a wide screen
read as ~1/3 horse between two thirds of empty grass. Now:
- `poem.html` carries `container_class = poem-permalink`; the poem lines are wrapped
  in `<div class="poem-block">`.
- In Fancy, the canvas widens to `max(720px, min(66vw, 1200px))` — ~2/3-viewport fill
  (Clover's 1/6 · 2/3 · 1/6 target), capped at 1200px on big desktops, **floored at
  720px** so it never goes narrower than the old column.
- `.poem-block` is `width: fit-content; margin-inline: auto` — the browser sizes it to
  the **longest line** and centres it, so lines keep a shared left edge (Clover's pick:
  left-aligned, not per-line-centred) while the block sits centred. Zero JS — the
  "measure the longest line" math is `fit-content`.
- Head / tags / footer stay capped at 720px so the dark note-boxes don't stretch into
  thin bars.
- **Plain + Reader untouched** — they ignore the class and keep the 720px card.

### Pasture grids — full width (all view modes)
My Pasture, Saved Horses, The Infinite Pasture carry `container_class = pasture-wide`
→ `min(94vw, 1500px)`. The chip grid is already flex-wrap, so widening the cap is all
it takes. **Scoped to these three templates only** — Saved Poems shares `.collection-page`
but stays a reading column. `.page-desc` stays capped at 640px for legibility.

### Mobile regression (caught by Clover, fixed same session)
First pass used `min(66vw, 1200px)` with no floor. 66vw only *exceeds* 720px above
~1090px viewport, so below that it made the canvas **narrower** than before — squishing
chips, wrapping names to two lines. Fix: the `max(720px, …)` floor (commit 2ac7c2e).
Desktop was wide enough to never expose it. **Lesson:** a `vw`-based widen needs a
px floor or it silently becomes a *narrow*-er on small viewports.

## Decisions made
- **Option C over per-line centring** — confirmed. Left-aligned block, centred as a
  unit via `fit-content`, matches Clover's typographic preference and "fill when space
  is available, stay compact when not."
- **Fancy only for the permalink; all-views for pastures** — confirmed. Plain/Reader
  permalink stays a calm 720px column (full width fights Reader's purpose); the pasture
  640px column was identical across modes so widening it once covers all three.
- **Scope by explicit container class, not `:has()`** — keeps Saved Poems out and is
  obvious to maintain.

## Uncertainty flags
None open.

## Testing holds
None. Clover live-verified desktop (permalink fill + pastures) and mobile (regression
fix) on poet.horse — "fixed, all good."

## Carryover
- Tunable knobs if proportions ever want adjusting: `max(720px, min(66vw, 1200px))`
  (permalink) and `min(94vw, 1500px)` (pastures), both in `static/style.css`.
- The infinite-scroll SVG fix (2.4 hold #2, PR #76) means wide Infinite Pasture renders
  real horses on scroll — confirmed compatible.

## Deferred / added to roadmap
Nothing deferred.
