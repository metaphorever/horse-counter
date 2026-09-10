# Phase 2.5.1 — Static pose variation (Fancy-view horses)

**Model:** Opus · **Effort:** high
**Depends on:** 2.4 (SVG chip art, separable parts), umbrella `spec/phase-2.5-horse-animation-overview.md`
**Status:** **AMENDED 2026-09-10** — art model changed from hand-drawn frame-sets
to *posable segments, posed and baked by Claude*. See **The art**. Runtime plan
unchanged. **Design sprint before full production.** Parts template + posing
harness shipped 2026-09-10 (see *Build order*, step 1).
**Ships:** per-render varied leg stance + head angle + facing for every server-rendered Fancy chip. **No animation, no layout change.**

The first move of the horse-animation arc. A poem of Fancy horses currently renders
every horse in the *same* pose — same legs, same head, same facing logic — so a
herd looks like clones. This phase gives each rendered horse a **plausible, varied
static pose**, selected from a purpose-built standing pool.

It is deliberately the **first** phase because it does the scary part — building
the posable horse and standing up the pose/bake pipeline — at the lowest stakes:
no motion, no layout, no JS dependency. Everything 2.5.2 (walk-cycle) and 2.5.3
(wander) need is built and proven here, statically. **That makes 2.5.1 the art
gate for the whole arc, not just for this phase:** every gait and every stance
downstream inherits these segments and these pivots.

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

## The art (Clover draws the parts — this is the gate)

**Amended 2026-09-10 (walk-cycle review session).** This phase originally asked
Clover to draw ~6 whole-leg frames per set, with static poses plucked from them.
That is **superseded**. Clover draws a small set of **posable segments** once;
Claude poses them numerically and **bakes the results into flat frame symbols at
build time**. The runtime is unchanged from the original plan — the browser still
gets ordinary `<use href="#hz-…">` refs. No JS posing and no change to the no-JS
story; the only per-chip transform chain is the neck + head (two rotations),
written into the markup server-side. *(Wording corrected 2026-09-10, parts-template
session — this read "no per-chip transform chains", which contradicted the
runtime-posed head below.)*

### Why the change

The walk cycle Clover drew (`prototypes/horse-chip-art-walk.svg` — 8 frames × 4
legs) was measured leg by leg and is a **trot**, not a walk: both diagonal pairs
land and lift in unison 4 frames apart, where a walk is 4-beat LH→LF→RH→RF.
Normalised hoof position is effectively identical frame-for-frame between
fore-near/hind-far and fore-far/hind-near.

Three further defects share one root cause — drawing frames in isolation, so the
ground reference and body anchors drift between them:

| Defect | Measured |
|---|---|
| Stance hooves not on one ground line | only 8 of 32 drawings land within 3u of y=339; stance ends float 4–13u high |
| Uneven stance spacing (the horse skates) | per-frame travel 17.8u–63.8u where all should be ~38u; fore stride 156–161u vs hind 145–147u |
| Hind legs skim | peak hoof clearance 20u hind vs 50u fore |

Posing from fixed pivots makes those three **impossible by construction** rather
than fixed by eye: the pivot does not move, and the hoof position is computed.

The deciding argument, though, is volume rather than correctness. Staying
frame-based costs Clover **~38 drawings** across the arc — walk ≈16, trot ≈16
(**a trot is not a retimed walk**: it has a suspension phase and much higher
flight), plus graze/idle/turning. Posable costs **~10 pieces once**, and every
later pose is a script run. Clover's drawing availability is the stated bottleneck
for the whole arc, so this is the constraint that matters.

### The pieces (10)

| Piece | Segments | Pivots / notes |
|---|---|---|
| **Front bumper** | 1 (static) | none — chest + shoulder mass; fills the barrel's front bottom corner |
| **Hind bumper** | 1 (static) | none — haunch; fills the rear bottom corner |
| **Fore leg** | 3 — forearm, cannon, hoof/pastern | elbow, knee, fetlock |
| **Hind leg** | 3 — gaskin, cannon, hoof/pastern | stifle, hock, fetlock |
| **Neck** + **Head** | 2 | withers, poll |
| **Tail** | hand-drawn, 4 static positions | none — not posable, see below |
| **Barrel** | unchanged stretchy `<rect>` | none |

**The bumpers are structural, not cosmetic.** They cover the shoulder and the hip,
so those two joints — the hardest to keep merged at every angle — are never
visible and never have to be drawn at all. That is why the posable chains start at
the **elbow** and the **stifle** rather than at the body. The bumpers also fix a
real defect found in review: the barrel's square bottom corners show on several
frames, because whole-leg art carries shoulder/haunch padding that leg-only art
lost (production `hz-lfn` spans 64u across the belly line; the walk frames vary
35u–75u).

**Static haunch is a deliberate simplification with a named fallback.** It may read
stiff at full hind extension. At 26px it should be fine; if it looks locked in
preview, promote the haunch to a fourth posable segment — additive, not a
redesign. **Clover checks this at the first prototype.**

**Head split into neck + head is justified specifically by Graze.** A rigid
head+neck rotating about a withers pivot points the muzzle down at grazing depth
instead of levelling at the ground, and drags the chest with it. If Graze were
ever dropped, one segment would do.

### Tail — stays hand-drawn (4 positions)

Posability buys least here and risks most: a big flowing shape is where a
segmented chain most obviously reads as a puppet, and the pose vocabulary needed
is tiny (swish is *timing*, not pose variety). Four positions, all from the
existing dock at the rear seam:

1. **Neutral hang** — the current tail, unchanged. Standing, grazing, slow walk.
2. **Forward swish** — lower two-thirds swung toward the head, tip curling under.
3. **Back swish** — swung away, tip trailing. The opposite beat.
4. **Lifted** — dock raised, carried higher and flagged out. Trot; alert/famous.

Alternating 2/3 reads as a swish, 1 is rest, 4 is gait-dependent. **Claude ships
rough warped versions of the existing tail path with the parts template**; Clover
cleans up or redraws keeping the rough shape. Low priority, easy to swap later.

### Drawing rules

Carried from 2.4: flat fill per part (coat applied in code via `currentColor`);
back line `y=110`, belly `y=210`, seams `x=150 / x=550`; the barrel zone stretches
so all shaping lives in the caps.

**Ground line is `y=344.5`** *(amended 2026-09-10, parts-template session; was
`y≈342`)*. 342 averaged all four production legs (`hz-lff` 344.5, `hz-lhn` 343.7,
`hz-lhf` 341.3, `hz-lfn` 339.8), but the posable rig reuses the near legs' shapes
for the far legs, and the number has to match the **fore**: it is the straight
leg, and making a near-straight leg 0.5u shorter costs ~11° of knee bend. At 344.5
the neutral pose is exactly today's horse, so nothing moves on the live site and
`--hz-y` needs no retune. The 2.4 template's `y=315` guide is vestigial and the
walk cycle drifted to 339. **One number, stated once in the template**
(`ground-line`).

New and load-bearing for posable:

- **Every segment carries a circular cap at its pivot end**, radius ≥ half the
  segment width, centred exactly on the pivot. This is what keeps the silhouette
  merged at every angle. At 26px a leg is 4–6px wide, so the rounding is
  sub-pixel — and `.hz` is **26px on every surface sitewide** (verified: the Fancy
  full-width work widened the *container*, not the horse), so there is no larger
  scale where it would show. *Exception (2026-09-10):* the neck root is ~114u
  wide, and a full-width cap made the chest a ball. The withers cap is r=46; the
  band just past the cut that it can't reach belongs to the static front bumper,
  so the rotating neck's root is exactly its round cap.
- **Pivots are marked in art coordinates and are the contract.** Moving one later
  invalidates every baked pose — cheap to regenerate, but all poses need
  re-validating.
- Segments must read correctly across their **whole** joint range, not in one
  pose. The harness shows the range live so this is checkable *during* the sprint.

## Two frame pools, not one

The original spec drew static poses from the walk-cycle frames because that was
the only art available. Posable removes the constraint, and the two pools have
genuinely different natural sizes:

| Pool | Size | Why |
|---|---|---|
| **Standing** (ships this phase) | as many as read well | Purpose-built: weight on all four, one hind resting, head at various heights. **A standing horse is not a walk frame held still** — this pool is what 2.5.1 actually ships and it reads considerably better than paused cycle frames. |
| **Walk cycle** (2.5.2) | **16** | Displayed frames per cycle = fps × stride duration. A horse walks ~1 stride/sec, so 16 frames ⇒ 16fps — which is also the "charming jank" register we want. Baking beyond that renders frames nobody sees. |

Frame-count arithmetic at chip scale (stride 304u = 79px of hoof travel):
8 frames ≈ 10px/step · **16 ≈ 5px** · 32 ≈ 2.5px · 64 ≈ 1.2px. Below ~2px per
step nothing is perceptible at 26px, so 32+ buys smoothness only at frame rates
we are deliberately not running.

**Page weight:** ~6 paths per baked frame at ~400 bytes ⇒ 16 frames ≈ 38KB raw in
`<defs>`, 64 ≈ 154KB, injected on every Fancy page. *Mitigation (2.5.2):* gate the
walk frames behind the animation setting so static-only pages carry the standing
pool alone.

## Pose selection (server-side, per render)

Pose is computed in Python during the **existing per-horse enrichment** (routes
already enrich `coat` / `rev` / `is_famous` before render — pose joins them). New
fields on the enriched horse dict:

- `leg_stance` — one entry from the **standing pool** (see *Two frame pools*).
  Each entry is a whole validated four-leg stance baked as symbols, not a per-leg
  roll, so implausible combinations cannot occur. Ground contact is exact by
  construction; the old **"≥3 of 4 hooves on the ground"** rule of thumb is now a
  *generation* constraint in the posing script rather than a hand-validation step.
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

- **`_horse_sprite.html`** — **generated, not hand-edited.** Legs become baked
  frame-sets `#hz-lff-0..N` / `#hz-lhf-0..N` (front/hind), each symbol holding the
  posed segments as flat paths. Bumpers get their own symbols. Head/neck stay
  *runtime*-posed (a CSS rotate, as originally specced) — they are the one part
  where continuous range beats baked steps, and it is 2 joints, not 14. Tail gains
  its static positions `#hz-tail-0..3`. Eye/nostril stay inside the head symbol
  (single tweak point, 2.4).
- **`tools/pose_horse.py`** (new) — the posing/bake step. Holds the segment
  geometry, the joint-limit constraints, the pose tables (standing pool + walk
  cycle) and emits `_horse_sprite.html`. **The pose tables are a plain list of
  angles — a knob set Clover can scrub**, in the same idiom as the `--hz-y`
  live-tuning knob from 2.4. Re-running it is the whole cost of a new pose.
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
- **Style drift — the highest-weighted risk.** Segmented limbs pull toward smooth
  and mechanical; the 2.4 look is chunky and hand-cut. **Claude cannot self-assess
  this** — measuring a generated SVG is reliable, judging whether it reads as a
  puppet is not. Clover is the eyes on every posed output, not just on the parts.
- **Numerically correct can be lifeless.** Joint angles derived from real gait data
  give an accurate medical-illustration walk; hand-drawn frames had character.
  Mitigation: the pose table is a tunable angle list, not a re-render.
- **Longer feedback loop.** Segments look like nothing on their own — correctness
  only appears after posing. Mitigation: **placeholder parts ship inside the
  harness first**, so Clover styles over geometry that is already proven and sees
  a wrong pivot immediately.
- **Stance plausibility** is now a generation constraint (whole validated stances
  are baked as symbols), so implausible per-leg combinations cannot be emitted.
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
- **`filter: drop-shadow` under animation (2.5.2 risk, flagged early).** Each chip
  `<svg>` carries a drop-shadow, and a filter re-rasterises its whole region on
  *any* change inside it. That cost is identical for frame-swapping and for
  runtime posing, so it is not an argument between them — but it is the thing most
  likely to make 2.5.2 stutter with 150 chips on screen. **Lower frame rate is the
  cheapest lever**: 15fps costs a quarter of 60fps, and lands in the "charming
  jank" register anyway. Test before committing to gait art.
- **Frame-swap mechanism is still open (2.5.2).** CSS cannot animate `<use href>`,
  so it is SMIL `calcMode="discrete"`, a sprite-strip translate, or JS — each with
  different reduced-motion and no-JS behaviour. Interacts with frame count. Not
  this phase's problem; recorded so it is not rediscovered.

## Design sprint (before full production — same discipline as 2.4)

Not a single pass — a **design sprint**. Claude goes first this time:

1. **Claude ships the parts template** — best-guess shapes for all 10 pieces with
   pivots marked in art coordinates, **proportions measured out of Clover's 32
   walk drawings** (so it is in-style and in-proportion, not invented), plus rough
   warped tail positions, plus the posing harness with those placeholders already
   posed and moving.
2. **Clover's design sprint** — style over proven geometry, adjust where needed.
   Because the placeholders are derived from Clover's own art, the template may be
   substantially usable as-is.
3. **Claude poses** — standing pool + a corrected 4-beat walk, targeting Clover's
   own hoof positions from the walk cycle (corrected for the trot, the pinning and
   the spacing). Herd-density + length-ladder preview at chip scale.

Gate checks (carried from 2.4):
1. Poses read as **plausible standing horses**, and the silhouette still **merges
   into one flat coat shape** at every word length and every joint angle.
2. Variety is **legible, not chaotic** — a poem looks like a herd of individuals.
3. Head pivot range and facing flip compose cleanly with coats and the shimmer.
4. **New:** joints do not read as a puppet in motion, and the static haunch does
   not read as locked.

**Expect two rounds, not one** — pass 1 validates proportions and pivots, pass 2
fixes what only shows in motion. That is the normal shape of this work, not a
failure. **No full pose production before the sprint clears.**

## Build order

1. **Parts template + harness** (Claude) — 10 pieces with pivots, rough tails,
   placeholder-posed harness. ✅ **Shipped 2026-09-10:**
   `prototypes/horse-parts-template.svg` (generated by
   `prototypes/horse-parts-cut.py`) + `prototypes/horse-posing-harness.html`.
   Session log `sessions/2026-09-10-phase-2.5.1-parts-template.md`.
2. **Design sprint** (Clover) — style the parts; check the static haunch.
3. **Posing + bake** — `tools/pose_horse.py`; standing pool, corrected walk;
   generate `_horse_sprite.html`.
4. **Pose enrichment + macro** — `_assign_pose`, `horse_svg(h)` (unchanged from
   the original plan — it still just picks symbol ids).
5. **Shimmer mask fix** + style (head `transform-origin`) + print/popover checks.
6. **Live verification** (Clover) — Fancy permalink + pasture + saved-horses +
   profile bio + queue show varied plausible poses; Plain/Reader/editor/counter
   unchanged; famous shimmer correct; reduced-motion + no-JS still render a pose.

## Files touched

- `templates/_horse_sprite.html` — **generated** by the posing script: baked leg
  frame-sets, bumper symbols, head/neck pivot, tail positions.
- `tools/pose_horse.py` **(new)** — segment geometry, joint limits, pose tables,
  sprite emitter. The pose tables are the tuning surface.
- `prototypes/` — parts template, posing harness, and the 2026-09-09 gait
  reference kit (walk SVG + analysis).
- `templates/macros.html` — `horse_svg(h)` emits selected frames + head rotate.
- `app.py` / `poetry.py` — `_assign_pose(h)` in the enrichment path.
- `static/style.css` — head `transform-origin`; per-angle rules.
- `static/horse-shimmer.js` — mask reads rendered frames.
- New art → wherever the sprite reads its part geometry.
- **Untouched:** Plain/Reader, editor templates, counter (`matcher.py` /
  `.horse-link`), `pasture.html` `chipHTML()` JS const.

---

## Open questions

1. **Static haunch** — does it read stiff at full hind extension? *Clover checks at
   first prototype; fallback is a fourth hind segment.*
2. **Standing-pool size** — how many stances before it feels varied enough?
   *Tune at the sprint; it is a script parameter now, not art.*
3. **Head-angle distribution** — weight toward neutral, or flat random across the
   range? *Tune at the sprint (code-side knob).*
4. **Resolved (2026-09-10):** frame count ⇒ **16** for the walk. Near/far leg sets
   ⇒ **one set, shaded and phase-offset** (the posable model dissolves the
   question). Tail ⇒ **hand-drawn**, 4 positions.
5. **Graze reach** *(found 2026-09-10)* — with the 2.4 neck, the lowest head
   position hangs at chest height, not at the grass, even with the neck-root pivot
   (`pv-withers`) placed deep in the chest for the longest lever. Lengthen the
   neck in the design sprint, or accept "head low" as graze? *Clover at the sprint.*
6. **Withers mane tuft** *(found 2026-09-10)* — the last mane teeth past the
   neck-root cut belong to the static front bumper, so they stay put as a tuft
   when the head drops. Keep, trim, or redraw? *Clover at the sprint.*

