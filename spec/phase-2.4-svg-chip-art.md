# Phase 2.4 — SVG chip art system (Fancy-view poems)

**Model:** Opus · **Effort:** high
**Depends on:** 1.12 (three-mode display system), 1.29 (DRY `render_chip` macro)
**Status:** spec + art FINAL, prototype gate PASSED (2026-06-18) — ready to build
**Promotes:** the "SVG chip art system" backlog item (Clover, 2026-05-23)
**Art source:** [prototypes/horse-chip-art.svg](../prototypes/horse-chip-art.svg) (Clover, final)

Replace the CSS/Unicode "found-objects" horse on **Fancy-view poems** with a real,
sliced SVG horse: fixed head + tail caps, a horizontally-stretchable barrel that
holds the horse's name, and four independently-addressable legs. One base
silhouette, coat-tinted via CSS. Drawn by Clover; integrated by Claude.

---

## Problem

The Fancy-view poem horse today is a pile of CSS tricks on `.poem-horse`
([static/style.css:1322](../static/style.css)):

```
::before  content:'♞'  + four leg stubs as background-gradient slices
::after   content:'∫'  (flipped) as the tail
.poem-horse  the coat-colored box = the body
```

Three problems, in priority order:

1. **Glyph drift.** `♞` and `∫` are font glyphs — the single most visually
   defining parts of the horse render differently across OS, browser, and font
   stack. The horse's identity is at the mercy of whatever font is installed.
2. **Motion dead-end.** Gradient-slice legs cannot do a walk/gallop cycle. The
   roaming/animation ambitions (backlog: "Fancy-mode motion + roaming
   sub-toggles") are blocked until legs become animatable path groups. **This is
   the enabling tech for that work, not just polish.**
3. **No room for real coat texture.** Flat fills only; the spotted/blanket coat
   patterns (backlog: "SVG coat pattern overlays") need a layered SVG to clip a
   pattern into the silhouette — impossible with the glyph hack.

Charm is preserved by **deliberately crude/naive art ("charming jank")**, not by
keeping Unicode. Web1 soul is an art-direction choice, not a technical constraint.

---

## Scope

**In scope — Fancy-view poem surfaces only.** Every surface that renders through
`render_chip` ([templates/macros.html](../templates/macros.html)) under
`body.view-fancy`: poem permalinks, My Pasture, Saved Horses, profile bio poems,
the poem queue preview, RSS-linked poem pages, collection pages.

**Out of scope — untouched this phase:**
- **The counter** (`.horse-link`, [matcher.py:448](../matcher.py) /
  [static/style.css:567](../static/style.css)) — keeps its glyph hack. The SVG
  art is reusable there later; logged as a ROADMAP follow-up. The counter is
  view-independent and a separate render path, so leaving it alone is clean.
- **Plain view** — flat coat tiles, readability-first. Unchanged.
- **Reader view** — plain text. Unchanged.
- **The editor canvas** — uses `.horse-tile` / `.stable-tiles`, a different
  class, so the `body.view-fancy .poem-horse` selector never reaches it. The
  1.12 "editor stays utilitarian" guarantee holds by class separation.
- **Coat patterns** (spots/blanket) — reserve the layer, build flat fill only.
- **Walk/gallop animation** — build the art *animation-ready* (separable legs,
  named pivots), but ship static. Animation is its own later phase with its own
  spec.

---

## The art: coordinate contract

The base silhouette is drawn on a single shared coordinate frame so the seams
line up by construction. Template file (guides + named empty groups) lives at
[prototypes/horse-chip-template.svg](../prototypes/horse-chip-template.svg).

**Canonical frame** (SVG user units, y down):

| Guide | Coord | Role |
|---|---|---|
| Back line | `y = 110` | barrel top; head crest + tail dock meet here |
| Belly line | `y = 210` | barrel bottom; all four leg pivots sit here |
| Ground line | `y = 315` | every hoof lands here |
| Front seam | `x = 150` | head ↔ barrel join |
| Rear seam | `x = 550` | tail ↔ barrel join |
| Nominal barrel | `x 150..550` (w 400) | "medium" word; **this zone stretches** |

**Corner anchors:** A `(150,110)` · B `(150,210)` · C `(550,110)` · D `(550,210)`.
**Leg pivots:** front `(185,210)` & `(220,210)`; hind `(480,210)` & `(515,210)`.

**Drawing rules:**
1. Barrel back (`y110`) and belly (`y210`) stay **dead straight** between the
   seams — that zone stretches horizontally; curves there smear. All shaping
   lives in the caps.
2. **Overlap, don't butt:** each appendage runs **8u** past its seam into the
   barrel (head → `x158`, tail → `x542`, leg tops → `y202`). The barrel paints
   over the overlap, hiding small misalignment.
3. One layer per part, named exactly: `head`, `barrel`, `tail`,
   `leg-front-near`, `leg-front-far`, `leg-hind-near`, `leg-hind-far`.
4. Legs hinge from their top-center pivot on the belly line; swing envelope
   ~±18u so a galloping leg never collides with its neighbor. Neutral standing
   stance.
5. Flat fill per part, no gradients. Coat color is applied in code.

Proportions are a tunable starting point; the *framework* (named parts, flat
barrel, 8u overlap, belly-line pivots) is fixed. If Clover re-proportions while
drawing, the new numbers become canonical and the slice constants update to match.

---

## Render technique — 9-slice via `<symbol>` + `<use>`

The chip is the barrel: the `<a class="poem-horse">` box holds the coat
background and the name text, exactly as today. The new parts are SVG layers
positioned around it.

**Page-level sprite (once per fancy page).** A hidden `<svg>` holding the part
geometry as `<symbol>`s, injected from a `horse_sprite()` macro in
[templates/base.html](../templates/base.html), gated on
`view_mode == 'fancy' and not is_admin_page`:

```html
<svg class="horse-sprite" aria-hidden="true" style="position:absolute;width:0;height:0">
  <defs>
    <symbol id="hz-head" viewBox="...">…fill="currentColor"…</symbol>
    <symbol id="hz-tail" viewBox="...">…</symbol>
    <symbol id="hz-barrel" viewBox="...">…</symbol>
    <symbol id="hz-leg" viewBox="...">…</symbol>
  </defs>
</svg>
```

**Per-chip markup (emitted by `render_chip`).** The macro adds the SVG layers
inside the existing `<a>`/`<span>`; they are `display:none` except under
`body.view-fancy`, so Plain/Reader DOM is unaffected visually:

```html
<a class="poem-horse coat-bay" data-name="…" href="…" style="--bg:…;--fg:…">
  <svg class="hz-layer hz-barrel" preserveAspectRatio="none"><use href="#hz-barrel"/></svg>
  <svg class="hz-layer hz-head"><use href="#hz-head"/></svg>
  <svg class="hz-layer hz-tail"><use href="#hz-tail"/></svg>
  <svg class="hz-layer hz-leg lf-near"><use href="#hz-leg"/></svg>
  <svg class="hz-layer hz-leg lf-far"><use href="#hz-leg"/></svg>
  <svg class="hz-layer hz-leg lh-near"><use href="#hz-leg"/></svg>
  <svg class="hz-layer hz-leg lh-far"><use href="#hz-leg"/></svg>
  <span class="hz-word">Display Name</span>
</a>
```

**How the slice behaves:**
- **Barrel** — `position:absolute; inset:0; width:100%; height:100%` with
  `preserveAspectRatio="none"`, so it stretches to the chip (= word) width. Flat
  edges → no visible distortion.
- **Head** — fixed px, absolutely positioned overhanging the chip's **left**
  edge, neck overlapping inward by the 8u-equivalent.
- **Tail** — fixed px, overhanging the **right** edge.
- **Legs** — fixed px; front pair anchored at fixed offsets from the chip's
  **left** edge, hind pair from the **right** edge. The belly-to-belly gap grows
  with the word — anatomically, a longer name = a longer-barrelled horse.

**Coat color:** symbol shapes use `fill="currentColor"`; the chip sets
`color: var(--bg)` (the coat var, already wired by `body.view-decorated
.coat-*`). Every `<use>` renders in the coat color, recolor "once, everywhere"
preserved. (Single-color now; the future pattern overlay adds a second `<use>`
layer with a `<pattern>` fill clipped to the silhouette — out of scope here, but
`currentColor` + layered symbols is the structure that allows it.)

**Facing (`rev`):** `transform: scaleX(-1)` on the chip flips all SVG layers;
`.hz-word` gets a counter `scaleX(-1)` so text stays readable. (Today's `rev`
class already exists from `_tile_appearance`.)

**Scale constant:** canonical 100u barrel height maps to the real chip text
height (~22–26px). One `--hz-scale` (or computed px constants) converts canonical
offsets (head width, leg pivot offsets, overlap) to CSS px. Defined once.

---

## CSS scoping

- Default: `.poem-horse .hz-layer { display: none }` — Plain/Reader/editor see
  nothing new.
- `body.view-fancy .poem-horse .hz-layer { display: block }` — turns the horse on.
- The **old** `body.view-fancy .poem-horse::before/::after` block and the leg
  gradients are **deleted** (replaced, not layered).
- **Per-coat Fancy tilt** (`body.view-fancy .coat-* { transform: rotate(…) }`,
  [style.css:1313](../static/style.css)) — open question, resolve at prototype:
  keep the jaunty tilt on the whole horse, or drop it. Lean keep.

---

## Edge cases & risks

- **Very short names.** A 2–3 char horse makes a barrel narrower than
  front-offset + hind-offset → front and hind legs could cross or the head/tail
  could touch. Mitigation: a **min barrel width** (clamp) so the shortest horse
  still shows four distinct legs and a readable body. The current gradient legs
  sit at 5/13px from the edges, so short names already work today — match or
  beat that floor. Verify at prototype with the shortest real horse names.
- **DOM weight.** A 40-horse poem = 40 chips × up-to-7 `<use>` refs = ~280
  `<use>` elements, all referencing 4 symbols. `<use>` is cheap (no geometry
  duplication), but verify scroll/paint on a long poem on a mid phone.
- **`<use>` + `currentColor` recolor** — well-supported, but confirm in target
  browsers (esp. older Safari) that per-chip `color` cascades into the `<use>`
  shadow tree. Fallback if not: inline `fill` via CSS var on the symbol shapes.
- **Print stylesheet** — Fancy isn't the print surface (print uses the Reader/
  print aesthetic), so SVG horses should not reach `@media print`. Confirm the
  sprite + layers are suppressed in print.
- **Accessibility** — SVG layers are decorative: sprite `aria-hidden="true"`;
  the accessible name stays the `<a>`/`.hz-word` text. The popover wiring
  (`data-name`, `.poem-horse` click delegation in
  [templates/_horse_popover.html](../templates/_horse_popover.html)) must still
  resolve — confirm clicks on an SVG layer bubble to the `.poem-horse` handler
  (event delegation already keys on `closest('.poem-horse')`, so this should
  hold; verify the layers don't swallow the click or break `el.textContent`
  reading the display name — may need `pointer-events:none` on `.hz-layer`).

---

## Prototype gate — PASSED (2026-06-18)

Resolved over three art iterations (head scaled down, then legs shortened) with
length-ladder + min-width previews. **Gate cleared by Clover: "Looks perfect."**
The build below is turnkey from here — no more open art questions.

---

## BUILD-READY CONSTANTS (gate output — start here next session)

**Art source:** `prototypes/horse-chip-art.svg` — Clover's final. Contains the 7
part shapes **plus a `GUIDES` layer to strip on import**, and Illustrator left the
leg ids jumbled (`leg-front-near`, `leg-front-near1`, `leg-hind-far`,
`leg-hind-near`, `leg-hind-near1`). **On import, rename to the 4 canonical ids**
by bbox (see table): two front legs (anchor left), two hind legs (anchor right).

**Canonical frame:** front seam `x=150`, rear seam `x=550`, back `y=110`, belly
`y=210`. Barrel rect = `150,110,400,100`. Hooves land at `y≈343` (the art's real
ground; my earlier `y=315` guess is superseded — slice to the art).

**Measured part bounding boxes (final art):**

| Part | bbox `x0,y0,x1,y1` | anchor |
|---|---|---|
| head | `32.7, 2.9, 303.0, 203.5` | left (front) |
| tail | `370.1, 98.4, 610.9, 277.1` | right (rear) |
| leg-front-far | `144.7, 165.0, 220.4, 344.5` | left |
| leg-front-near | `174.8, 162.6, 251.6, 339.8` | left |
| leg-hind-far | `445.5, 168.9, 514.1, 341.3` | right |
| leg-hind-near | `481.5, 172.0, 553.0, 343.7` | right |

**Per-part placement** (proven in the prototype; `s` = scale = chip barrel-height
px ÷ 100; `W` = chip content width):
- part `<svg>` `viewBox = "x0 y0 (x1−x0) (y1−y0)"`, size = `(w·s) × (h·s)`
- `top = (y0 − 110)·s`
- `left = `  left-anchored: `(x0 − 150)·s`  ·  right-anchored: `W − (550 − x0)·s`
- The chip element **is** the barrel: coat background fills the torso band; the
  word sits on it (`z-index` above parts). All parts share the coat fill, so
  head/barrel/tail/legs **merge into one flat silhouette** — this is the intended
  look and is what makes the deep head/tail overlap (head→x303, tail→x370)
  forgiving at every length.

**Minimum-length floor:** `min-width: 6ch` on the chip (plus its horizontal
padding), `text-align:center`. Names < 6 chars clamp to the 6-char body and
center; ≥ 6 grow naturally. Self-adjusting because the chip font is monospace —
no pixel constant to drift. (Chosen by Clover at the "Empire" length.)

**Production translation of the prototype:** the gate prototype composited each
part as an absolutely-positioned `<svg>` with the coat fill inline. Production
swaps that for one page-level `<defs>` of `<symbol>`s (`fill="currentColor"`) +
per-chip `<use href="#…">`, with the chip setting `color: var(--bg)` so the 8
coats recolor for free. `.hz-layer { pointer-events:none }` so popover clicks
still bubble to `.poem-horse`. Geometry/placement math is unchanged.

---

## Build order

## Build order

1. ~~**Art** (Clover)~~ ✅ DONE — final art at `prototypes/horse-chip-art.svg`,
   gate passed 2026-06-18. Constants captured above.
2. **Slice + one coat** — sprite symbols, the 4 part types, scale constant, the
   stretch/positioning CSS; reuse the prototype's placement math (above).
3. **All coats + `rev`** — confirm `currentColor` recolor across the 8 coats and
   both facings; resolve the Fancy-tilt question.
4. **Macro + scoping** — `render_chip` emits the layers; `horse_sprite()` in
   base.html; delete the old `::before/::after` block; min-width clamp; print +
   popover + pointer-events checks.
5. **Live verification** (Clover) — Fancy poems across permalink, pasture,
   saved-horses, profile bio, queue; Plain/Reader/editor unchanged; popover
   still opens; mobile scroll on a long poem.

---

## Open questions

1. **Fancy per-coat tilt** — keep or drop once a real horse sits in the chip
   (decide during live verification). *Still open.*
2. ~~Min barrel width~~ ✅ RESOLVED — `min-width: 6ch`, centered (Clover, "Empire" length).
3. **`<use>`/`currentColor` recolor** in older Safari — confirm, else inline-var
   fallback. *Still open (build-time check).*
4. ~~Proportions~~ ✅ RESOLVED — final art measured; constants above.

---

## Files touched

- `templates/macros.html` — `render_chip` emits SVG layers; new `horse_sprite()`.
- `templates/base.html` — inject `horse_sprite()` once, gated on Fancy.
- `static/style.css` — new `.hz-*` layer rules + Fancy scoping; **delete** the
  `body.view-fancy .poem-horse::before/::after` block and leg gradients.
- `prototypes/horse-chip-template.svg` — the drawing frame (already committed).
- New: the base silhouette SVG asset (Clover's art) → wherever the sprite reads it.
- **Untouched:** `matcher.py` / `.horse-link` (counter), the editor templates.
