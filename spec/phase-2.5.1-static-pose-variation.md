# Phase 2.5.1 — Static pose variation (Fancy-view horses)

**Model:** Opus · **Effort:** high
**Depends on:** 2.4 (SVG chip art, separable parts), umbrella `spec/phase-2.5-horse-animation-overview.md`
**Status:** spec FINAL pending Clover review; **art gate before full production**
**Ships:** per-render varied leg stance + head angle + facing for every server-rendered Fancy chip. **No animation, no layout change.**

The first move of the horse-animation arc. A poem of Fancy horses currently renders
every horse in the *same* pose — same legs, same head, same facing logic — so a
herd looks like clones. This phase gives each rendered horse a **plausible, varied
static pose** by selecting frames from the (about-to-exist) walk-cycle library.

It is deliberately the **first** phase because it does the scary part — reworking
the 2.4 sprite into frame-sets and standing up the asset pipeline — at the lowest
stakes: no motion, no layout, no JS dependency. Everything 2.5.2 (walk-cycle) needs
is built and proven here, statically.

---

## Goal & non-goals

**Goal:** each server-rendered Fancy chip shows a randomly chosen, anatomically
plausible standing pose: a leg stance, a head angle, a tail position, and a
facing direction — varying per render, no-JS-friendly.

**Non-goals (explicitly out — later phases):**
- **No animation.** Legs/tail/head do not move. (2.5.2)
- **No layout change.** Horses stay in poem formation, inline flow. (2.5.3)
- **No control UI.** No View-menu tree, no strip, no persistence yet. Static
  variety is *always on* under Fancy (it replaces the single static pose). The
  control surface arrives with animation in 2.5.2.
- **No client-rendered surfaces.** The JS infinite-scroll pasture (`pasture.html`
  `chipHTML()`) keeps its current single pose this phase; it updates when its
  surface is brought into the system later. All **server-rendered** `render_chip`
  surfaces get variety for free (see Scope).

---

## Scope

Static variety is a **global `horse_svg()` macro change**, so it lands on every
surface that renders through `render_chip` server-side under `body.view-fancy`:
poem permalinks, My Pasture, Saved Horses, profile bio poems, the poem queue
preview. (Unlike Wander, which is permalink-first, static poses are cheap and
global — there's no reason to gate them per surface.)

**Untouched:** Plain / Reader views, the editor (`.horse-tile`), the counter
(`.horse-link`), and the JS-rendered infinite-scroll pasture const.

---

## The art (Clover draws — this is the gate)

This phase establishes the **full leg frame library**, because static poses are
drawn *from* the walk-cycle frames (one library serves both static and 2.5.2's
animation). Per the umbrella asset shape:

| Part | What to draw | Notes |
|---|---|---|
| **Front legs** | ~6-frame walk-cycle set | one set; near/far share it (far = shaded + phase-offset later). Each frame on the 2.4 coordinate frame (belly-line pivot `y=210`, hooves land `y≈343`). |
| **Hind legs** | ~6-frame walk-cycle set | same. |
| **Head** | one drawing + a marked **neck pivot point** | pivots across ~6 angles up↔down; grazing = fully lowered. A single `<use>`, rotated — *not* frames. |
| **Tail** | 2–4 static positions to start | static picks one; the full 4–6 swish set can finish in 2.5.2. |
| **Barrel** | unchanged | the stretchy `<rect>` from 2.4. |

**Drawing rules carry over from 2.4:** flat fill per part (coat applied in code via
`currentColor`); 8u seam overlap so parts merge into one flat silhouette; back
line `y=110`, belly `y=210`, seams `x=150 / x=550`. **Each leg frame must keep its
top anchored at its belly-line pivot** so swapping frames doesn't shift the leg's
attachment — only the hoof end moves. Mark the head's neck pivot in art coords so
CSS `transform-origin` can rotate it cleanly.

**Frame count is a starting point, tunable at the gate** — fewer if 6 reads as
busy, the framework (front-set / hind-set / pivot-head / tail-set) is fixed.

---

## Pose selection (server-side, per render)

Pose is computed in Python during the **existing per-horse enrichment** (routes
already enrich `coat` / `rev` / `is_famous` before render — pose joins them). New
fields on the enriched horse dict:

- `leg_stance` — one entry from a **curated stance set**: a list of
  `(front_frame, hind_frame)` combinations hand-validated to look like a real
  standing horse. The validation rule of thumb is **"≥3 of 4 hooves on the
  ground"** — start with a small curated set, then experiment to find what reads
  best (the rule is a tunable, not a hard constraint baked in code).
- `head_angle` — one of the ~6 head pivot steps (weight toward neutral so most
  horses look alert, a few graze/look-up).
- `tail_frame` — one of the static tail positions.
- `rev` — **randomized facing** (this phase makes facing random for variety,
  extending today's `_tile_appearance` `rev`).

**Randomized, not hashed.** Random and hash cost the same, and Clover wants fresh
poses each load — so `random.choice` per render. (If a future feature ever needs a
*stable* per-horse pose, switch the seed to `hash(name)` in one place — noted, not
built.)

`horse_svg()` (today arg-less) **takes the enriched horse** and emits the selected
frame `<use href="#hz-lff-N">` / head `transform` rotate / tail `<use>` / `rev`
accordingly. Same render path as 2.4 — only *which* frame and *what* head angle
change.

---

## Sprite & macro changes

- **`_horse_sprite.html`** — legs become frame-sets: `#hz-lff-0..N`,
  `#hz-lhf-0..N` (front/hind). Head symbol gains a documented neck-pivot origin.
  Tail gains its static positions `#hz-tail-0..M`. Eye/nostril stay inside the
  head symbol (single tweak point, 2.4).
- **`macros.html`** — `horse_svg(h)` reads `h.leg_stance / h.head_angle /
  h.tail_frame / h.rev`, emits the chosen `<use>`s and the head rotate transform.
  Draw order from 2.4 preserved (back→front: shaded far legs, tail, barrel, near
  legs, head).
- **Route enrichment** (`app.py` / `poetry.py` wherever coat/rev are set) — add
  `_assign_pose(h)` writing the four fields.
- **`static/style.css`** — head `transform-origin` at the neck pivot; any per-angle
  rule. No layout changes.
- **`static/horse-shimmer.js`** — the shimmer mask currently hardcodes the
  single-pose leg ids (`#hz-lff` etc.). It must mask the **actually rendered**
  frames — read the selected `<use href>`s from the chip's own SVG rather than
  hardcoding. (Build task; keep the reduced-motion / no-JS guards.)

---

## Risks & edge cases

- **Facing flip × head pivot.** `rev` applies `scaleX(-1)` to the chip; confirm the
  head rotate composes correctly under the flip (a rotate inside a mirrored frame
  flips sign — verify the grazing head still lowers, not raises, when reversed).
- **Stance plausibility at speed.** Independent per-leg random can produce
  floating/impossible stances. Mitigation: the **curated stance set** (pick a whole
  validated combo, not per-leg) — this is the safe default; per-leg-with-reroll is
  a fallback only if the curated set feels too repetitive.
- **Shimmer mask drift.** If the mask still points at old single-pose ids, famous
  horses shimmer a *different* silhouette than they render. Covered by the
  shimmer.js change above — verify on a famous horse in several poses.
- **Per-render instability is intended** — the same poem re-rendered shows
  different poses. Confirm this doesn't surprise anywhere that screenshots/caches
  poems (none known; flag if found).
- **DOM weight.** Frame-sets enlarge the sprite `<defs>` (~12 leg + a few tail
  symbols) but it's injected **once per page**; per-chip `<use>` count is
  unchanged from 2.4 (still 7-ish refs/chip). Verify the sprite size is fine.
- **Print** — Fancy isn't the print surface; confirm poses/sprite stay suppressed
  under `@media print` (inherited 2.4 guard).
- **Popover** — pose is decorative; `.hz-*` layers keep `pointer-events:none`,
  clicks still bubble to `.poem-horse`. Unchanged from 2.4 — verify.

---

## Art gate (before full production — same discipline as 2.4)

Clover draws a **starter set**: one front + one hind leg frame set (or a partial
set), the pivot head, and 1–2 tail positions. Claude wires the random
rule-constrained selection and renders a **herd-density + length-ladder preview**
at chip scale. Gate checks:
1. Poses read as **plausible standing horses** (the ground-contact rule looks
   right), and the silhouette still **merges into one flat coat shape** at every
   word length.
2. Variety is **legible, not chaotic** — a poem looks like a herd of individuals,
   not a glitch.
3. Head pivot range (up↔down) and facing flip both compose cleanly with coats and
   the famous shimmer.

**Gate passes → Clover finishes the full frame library → wire-in + live
verification.** No full art production before the gate clears.

---

## Build order

1. **Art gate** (Clover starter set → Claude preview → Clover "looks right").
2. **Sprite rework** — frame-set symbols, head pivot origin, tail positions.
3. **Pose enrichment + macro** — `_assign_pose`, `horse_svg(h)`, curated stance set.
4. **Shimmer mask fix** + style (head transform-origin) + print/popover checks.
5. **Live verification** (Clover) — Fancy permalink + pasture + saved-horses +
   profile bio + queue show varied plausible poses; Plain/Reader/editor/counter
   unchanged; famous shimmer correct; reduced-motion + no-JS still render a
   (static) pose.

---

## Files touched

- `templates/_horse_sprite.html` — leg frame-sets, head pivot, tail positions.
- `templates/macros.html` — `horse_svg(h)` emits selected frames + head rotate.
- `app.py` / `poetry.py` — `_assign_pose(h)` in the enrichment path.
- `static/style.css` — head `transform-origin`; per-angle rules.
- `static/horse-shimmer.js` — mask reads rendered frames.
- New art → wherever the sprite reads its part geometry.
- **Untouched:** Plain/Reader, editor templates, counter (`matcher.py` /
  `.horse-link`), `pasture.html` `chipHTML()` JS const.

---

## Open questions

1. **Frame count** — ~6 front / ~6 hind a good starting target, or fewer? *Resolve
   at the art gate.*
2. **Curated stance set size** — how many validated standing combos before it feels
   varied enough? *Tune at the gate.*
3. **Head-angle distribution** — weight toward neutral, or flat random across the 6
   steps? *Tune at the gate (low-stakes, code-side knob).*
