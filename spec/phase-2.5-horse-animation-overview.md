# Phase 2.5 — Horse animation (umbrella overview)

**Model:** Opus · **Effort:** high
**Depends on:** 2.4 (SVG chip art system — separable parts, single-`<svg>`-per-chip render)
**Status:** overview FINAL; Phase 2.5.1 specced; 2.5.2 / 2.5.3 to spec after 2.5.1 ships
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
| **2.5.1** | Static pose variation | Per-render varied stance + head angle + facing; no animation, no layout change | The sprite rework + the asset pipeline |
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

**Asset shape (Clover draws; gated before full production):**
- **Legs** — frame-based walk-cycle: a front-leg set + a hind-leg set, ~6 frames
  each. These frames double as the **static pose pool**.
- **Head** — a *single* drawing with a defined neck pivot, pivotable across ~6
  angles (all-the-way-up ↔ all-the-way-down/grazing). Not frames.
- **Tail** — 4–6 swish frames (can start with fewer; static picks one).
- **Barrel** — unchanged stretchy `<rect>`.

---

## Build order

1. **2.5.1 Static pose variation** — rework the sprite into frame-sets, draw the
   leg cycle + head + tail frames (the art gate), render a server-side random
   rule-constrained pose per horse. *Full spec: `spec/phase-2.5.1-static-pose-variation.md`.*
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
- **Per-gait timing / phase offsets** (2.5.2): walk = 4-beat, trot = 2-beat
  diagonal, graze = slow + grazing pauses. Mostly a timing-param library over the
  shared frames, not 3× the art.
