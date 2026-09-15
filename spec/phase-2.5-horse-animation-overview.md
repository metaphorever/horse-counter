# Phase 2.5 — Horse animation (umbrella overview)

**Model:** Opus · **Effort:** high
**Depends on:** 2.4 (SVG chip art system — separable parts, single-`<svg>`-per-chip render)
**Status:** overview FINAL; **asset shape AMENDED 2026-09-10** (posable segments,
posed and baked by Claude — see 2.5.1); 2.5.2 / 2.5.3 to spec after 2.5.1 ships
**Promotes:** the "Fancy-mode motion + roaming sub-toggles" backlog item (Clover, 2026-05-23)

This is the umbrella for bringing the Fancy-view horses to life: varied static
poses, a frame-based walk-cycle, and free roaming across the field. It records the
shared decisions, vocabulary, architecture, and build order. **Each sub-phase gets
its own full spec, written only once the previous one has shipped and its lessons
are in hand.** We deliberately do not over-spec the later phases here.

---

## Why three phases

The walk-cycle is frame-based (Clover's call) rather than a procedural leg-pivot.
That's a bigger lift than the original "swing the legs" idea, but it pays off
before any motion ships — a static horse can render a frame *plucked from the
cycle*, so a poem of horses stops looking like clones. That reframes the work into
three independently-shippable phases, each with a visible win, and — by design —
the scariest part (reworking the SVG sprite into frame-sets) happens **first, at
the lowest stakes**:

| Phase | Name | Ships | Risk it retires |
|---|---|---|---|
| **2.5.1** | Static pose variation | Per-render varied stance + head angle + facing; no animation, no layout change | The posable horse + the pose/bake pipeline — **the art gate for the whole arc** |
| **2.5.2** | Walk-cycle | Frame-animated legs + tail swish + head motion; "Hold Your Horses" (animate in place) | Animation technique + perf at herd scale |
| **2.5.3** | Wander | Horses roam the grass field; "Set Horses Loose" + gaits + Return to Formation | The layout break-out + the roaming controller |

Static pose variation lands **everywhere `render_chip` renders server-side** (it's
a cheap global macro change). The **Wander** feature is the one scoped
**permalink-first**, other Fancy surfaces later — it's the per-surface layout lift.

---

## Settled vocabulary & controls

**View menu becomes a small tree** (motion is decoupled from view per 1.12, but the
control lives *under* Fancy because animation only exists there):

```
VIEW:
▸ Fancy
    – No Animations          (static, varied poses — 2.5.1)
    – Horse Animations       (legs/tail/head animate — 2.5.2+)
– Plain
– Reader
```

**When "Horse Animations" is on, a try-on-style strip appears** (mirrors the
first-run view picker strip), holding:

| Control | Behavior |
|---|---|
| **Hold Your Horses** | Stop roaming; animate in place *wherever they currently are* (poem may still be scrambled) |
| **Set Horses Loose** | Roam the field (poem scrambles by design); reveals the gait options |
| **Return to Poem Formation** | Walk/snap back to rest positions so the poem reads again, landing in the Hold state |
| **Graze** | Slowest gait; pauses to graze with the head lowered |
| **Walk** | Medium gait |
| **Trot** | Faster gait |

`Hold Your Horses` and `Return to Poem Formation` are **distinct**: Hold freezes
roaming in place; Return restores formation. This **supersedes the old
"Scatter / Reform" vocabulary** in the backlog.

**Animation state persists as a view setting** (cookie / DB pref, like view-mode).
**`prefers-reduced-motion` forces the effective "No Animations" state** regardless
of the saved preference (1.12 motion-decoupling holds — reduced-motion suppresses
*within* the mode, it does not switch modes).

---

## Shared architecture (inherited from 2.4)

The 2.4 render survives largely intact; animation rides on top of it:
- **One `<svg>` per chip**, all parts in one coordinate space (`_horse_sprite.html`
  symbols referenced by `<use>` from `horse_svg()` in `macros.html`).
- **Coat via `currentColor`**; off-side legs shaded (Fore Y / Hind X); famous
  shimmer = masked whole-horse sweep (`static/horse-shimmer.js`).
- **No-JS core, JS as a treat.** Static poses are **server-emitted** (work with JS
  off). The walk-cycle is CSS/SMIL animation (degrades to a static frame with no
  JS / under reduced-motion). Wander is the one genuinely JS-dependent layer —
  no-JS users get the static poem, which is the correct graceful fallback.

**Asset shape — AMENDED 2026-09-10 (Clover draws the parts; gated before full
production).** Clover draws **posable segments once**; Claude poses them and
**bakes flat frame symbols at build time**. The runtime is unchanged — the browser
still gets ordinary `<use>` refs, no JS posing. Full rationale and measurements in
`spec/phase-2.5.1-static-pose-variation.md`.
- **Legs** — posable: fore = forearm/cannon/hoof (elbow, knee, fetlock); hind =
  gaskin/cannon/hoof (stifle, hock, fetlock). **One set, shaded and phase-offset
  for near/far.** Baked into a purpose-built **standing pool** (static) and a
  **16-frame walk cycle** (2.5.2) — two pools, different natural sizes.
- **Bumpers** — front (chest/shoulder) + hind (haunch), static. **Structural:**
  they hide the shoulder and hip joints so those never have to merge, and they
  fill the barrel's square bottom corners.
- **Head** — **neck + head, 2 segments**, runtime-posed via CSS rotate (the split
  is what makes grazing work). Not frames.
- **Tail** — **stays hand-drawn**, 4 static positions. Swish is timing, not pose
  vocabulary; a segmented chain is where a big flowing shape most reads as a
  puppet.
- **Barrel** — unchanged stretchy `<rect>`.
- **Superseded:** the original "~6 whole-leg frames per set, Clover draws each
  frame" plan. Reason: frames drawn in isolation drift on ground reference and
  body anchors (the 2026-09-09 walk cycle came out a **trot**, with unpinned
  hooves and uneven stance spacing), and the arc would cost ~38 drawings against
  ~10 posable pieces.

---

## Build order

1. **2.5.1 Static pose variation** — build the posable horse (Claude ships the
   parts template + harness → Clover's design sprint → Claude poses and bakes),
   then render a server-side random rule-constrained pose per horse. *Full spec:
   `spec/phase-2.5.1-static-pose-variation.md`.*
2. **2.5.2 Walk-cycle** — animate the frames; wire "Horse Animations / Hold Your
   Horses"; the View-menu tree + persistence; tail swish + head motion. *Spec
   after 2.5.1 ships.*
3. **2.5.3 Wander** — break chips out of inline flow onto the grass field; the
   roaming controller (random drift, edge + obstacle avoidance); gaits; Set Loose
   / Return to Formation. *Spec after 2.5.2 ships.*

---

## Deferred / future (not in this arc)

- **Carrot herding toy** (Clover, idea 2026-06-28) — grab a carrot from the
  control strip, drag it around the field, and the horses follow it. This is the
  *one* place real pathfinding would live (the rest of Wander is deliberately
  avoidance-only, no route-planning). A fun future addition once Wander exists —
  explicitly **not** in 2.5.3.
- **Ambient background horses** (existing backlog) — horses loose in the grass
  *behind* working UI. Separate surface from the poem chips; stays its own item.
- **SVG coat pattern overlays** (existing backlog) — orthogonal to motion.

---

## Open questions carried into the later sub-phase specs

Not blocking 2.5.1; resolve when its phase is specced.

- **Wander arena (2.5.3):** horses scroll *with* the page (settled) — confirm the
  roam region is the full document grass height vs. live viewport, and how
  obstacle rects (nav, control strip, info/popover boxes) are gathered.
- **Avoidance model (2.5.3):** soft repulsion from edges + UI rects, no
  route-planning. Open: do horses avoid *each other* or pass through? (Lean:
  pass through — "no complicated pathfinding.")
- **Clicking a roaming horse pauses it** (settled) — define what "pause" means
  (this horse only? resumes how?) at 2.5.3 spec time.
- **Per-gait poses** (2.5.2): walk = 4-beat lateral-sequence (LH→LF→RH→RF), trot =
  2-beat diagonal, graze = slow + grazing pauses. **Corrected 2026-09-10:** this
  previously read "mostly a timing-param library over the shared frames, not 3×
  the art". That is wrong for the trot — a trot has a **suspension phase and much
  higher hoof flight**, so retiming walk frames yields a fast walk, not a trot.
  Under the frame-based plan that was a second full art library; under the posable
  model it is a second pose table and costs no art at all. (This correction is a
  large part of why the asset shape changed.)
- **Frame-swap mechanism** (2.5.2): CSS cannot animate `<use href>` — SMIL
  `calcMode="discrete"`, a sprite-strip translate, or JS, each with different
  reduced-motion / no-JS behaviour. Interacts with frame count and frame rate.
- **Frame rate** (2.5.2): 60fps is not assumed. The per-chip `drop-shadow` filter
  re-rasterises on any change inside it, so **15fps costs a quarter of 60fps** and
  lands in the "charming jank" register anyway. Pick it live.
- **Stride vs body bob** (2.5.2 — found 2026-09-10 in the posing harness): a
  rigid leg pivoting at the elbow can't keep a stance hoof on the ground through
  a stride while the body stays fixed — a straight leg only touches down directly
  under its pivot. The harness pins hooves by bobbing the body: at a 100u stride
  the bob is 0–11.5u (**~3px** at chip scale); Clover's drawn ~156u stride would
  need ~9px. Options: accept a small bob (natural — real horses vault over the
  stance leg), shorten the stride, or add a scapula/femur segment (the
  static-haunch fallback, at both ends). A bob moves the barrel under the HTML
  name, so also decide whether the word rides with it.
  **Decided 2026-09-14 (Clover, from the harness "name" picker):**
  - **The name rides the bob, smoothly.** "Whole px" was rejected: the text
    snaps while the body slides, so they visibly drift apart.
  - **The bob becomes a user toggle.** Riding text is a little harder to read,
    and may cross the line for motion-sensitive readers who still want walking.
  - **No-bob = the unpinned walk**, the harness's "keep stance hooves on the
    ground" box unticked. Clover: it "looked fine to my eyes"; the bob is a
    little more real, and that's the tradeoff for readability.
  - **Cost to carry into the spec:** the pinned and unpinned walks solve the legs
    differently, so offering both means two baked walk sets (2 × 16 frames), or
    one walk if we ship only the unpinned one.
- **Idle animations (2.5.2)** — *Clover, 2026-09-14:* standing horses that
  still move now and then: lean down to graze, flick the tail, shift a leg,
  stretch. This is only partly covered today. 2.5.2 lists tail swish and head
  motion, and the Graze gait pauses to graze (2.5.3), but standing idles aren't
  named anywhere. Under the posable model they're cheap: head and tail are pose
  swaps, and a weight shift is a move between two standing-pool stances, so the
  2.5.1 pool doubles as idle keyframes. Scope them at 2.5.2 spec time.
- **Parade mode (2.5.3 candidate)** — *Clover, 2026-09-14,* prompted by the
  harness's lock-step length ladder: every horse in a poem walks the same way in
  lock-step, parading back and forth across the screen. The no-bob toggle
  applies here too. Place it when 2.5.3 is specced.
