#!/usr/bin/env python3
"""Generate the posable-horse parts template (Phase 2.5.1 design sprint).

Cuts the live 2.4 horse (templates/_horse_sprite.html) into the 10 posable
pieces from spec/phase-2.5.1-static-pose-variation.md, adds a circular cap at
every pivot, warps the existing tail into 4 rough positions, and writes an
Illustrator-friendly SVG with one named group per piece plus a PIVOTS layer.

Because the pieces are cut from the production art, the neutral pose
reproduces today's horse — the posing harness uses that as its sanity check.
The template is a *starting point*: once Clover restyles it, the edited SVG is
the source of truth and this script is not re-run over it.

Also refreshes the built-in copies (template, walk frames, production sprite)
inside prototypes/horse-posing-harness.html, so the harness stays one file.

Scratch-only deps (NOT app deps, not in requirements.txt): shapely, svgelements.
Run from the repo root:
    python3 -m venv /tmp/hz && /tmp/hz/bin/pip install shapely svgelements
    /tmp/hz/bin/python prototypes/horse-parts-cut.py
"""
import math
import re
import sys

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from svgelements import Close, Move, Path

SPRITE = 'templates/_horse_sprite.html'
WALK_REF = 'prototypes/horse-chip-art-walk.svg'      # Clover's 2026-09 walk frames (onion-skin reference)
OUT = 'prototypes/horse-parts-template.svg'
HARNESS = 'prototypes/horse-posing-harness.html'
GROUND = 344.5           # where the near fore's hoof stands in production (hind: 343.7). The spec's
                         # 342 averaged in the far legs; all four legs now reuse the near shapes.
                         # Pinned to the FORE because it's the straight leg: making a near-straight
                         # leg 0.5u shorter costs ~11° of knee bend, while the bent hind has slack.
CAP_PAD = 1.0            # cap radius = half the joint width + this
CAP_OVERRIDE = {'withers': 46.0}   # the neck root is ~114u wide; a full-width cap made the chest a
                                   # ball. The band this smaller cap can't reach goes to the bumper.
SIMPLIFY = 0.3           # polygon simplification tolerance, art units (0.08px at chip scale)

# ── Joint placement — TUNE HERE ─────────────────────────────────────────────
# Legs are cut with horizontal lines at these heights; each pivot sits at the
# middle of the leg's width at that height. Heights come from the production
# legs' own width profile (forearm taper ends ~y260, fetlock bulge ~y316,
# hock point ~y262), cross-checked against Clover's walk drawings.
FORE_CUTS = [('elbow', 214), ('knee', 260), ('fore-fetlock', 316)]
HIND_CUTS = [('stifle', 214), ('hock', 262), ('hind-fetlock', 320)]
# Neck/head cuts: (centre guess, cut direction). The pivot is the middle of the
# chord where the cut line crosses the silhouette. The withers pivot sits deep
# at the neck root (not on the back line) so lowering the neck has a long lever.
POLL_CUT = ((128, 68), (0.3, -1.0))
WITHERS_CUT = ((190, 142), (1.0, -0.9))
MUZZLE = (35, 100)        # any point on the head side of the poll cut
DOCK = (553, 113)         # tail root, for the warps


def sprite_path(src, pid):
    m = re.search(r'id="%s"[^>]*d="([^"]+)"' % pid, src)
    if not m:  # since 2.5.1 the sprite is baked from Clover's parts; this script cuts the 2.4 horse
        sys.exit(f'{SPRITE} has no #{pid}: it is the baked 2.5.1 sprite now. This script cuts the 2.4 '
                 'horse; point SPRITE at a copy of it from git (git show 52312fe:templates/_horse_sprite.html).')
    return m.group(1)


def to_geom(d, step=1.2):
    """Sample an SVG path into a shapely geometry; subpaths combine even-odd so
    the head's nostril/brow cut-outs stay holes."""
    rings, ring = [], []
    for seg in Path(d).segments():
        if isinstance(seg, Move):
            if len(ring) > 2:
                rings.append(ring)
            ring = [(seg.end.x, seg.end.y)]
            continue
        if isinstance(seg, Close):
            continue
        n = max(1, math.ceil(seg.length(error=1e-3) / step))
        ring += [(p.x, p.y) for p in (seg.point(i / n) for i in range(1, n + 1))]
    if len(ring) > 2:
        rings.append(ring)
    geom = None
    for r in rings:
        g = Polygon(r).buffer(0)
        geom = g if geom is None else geom.symmetric_difference(g)
    return geom


def halfplane(p, d, keep):
    """Big polygon on the side of line (p, d) that contains point `keep`."""
    dx, dy = d
    L = math.hypot(dx, dy)
    dx, dy = dx / L, dy / L
    nx, ny = -dy, dx
    if (keep[0] - p[0]) * nx + (keep[1] - p[1]) * ny < 0:
        nx, ny = -nx, -ny
    B = 2000
    return Polygon([(p[0] + dx * B, p[1] + dy * B), (p[0] + dx * B + nx * B, p[1] + dy * B + ny * B),
                    (p[0] - dx * B + nx * B, p[1] - dy * B + ny * B), (p[0] - dx * B, p[1] - dy * B)])


def chord(geom, p, d):
    """Where the cut line through p crosses the silhouette → (midpoint, half-length)."""
    dx, dy = d
    L = math.hypot(dx, dy)
    line = LineString([(p[0] - dx / L * 600, p[1] - dy / L * 600), (p[0] + dx / L * 600, p[1] + dy / L * 600)])
    hit = geom.intersection(line)
    pieces = list(getattr(hit, 'geoms', [hit]))
    piece = min(pieces, key=lambda s: s.distance(Point(p)))
    mid = piece.interpolate(0.5, normalized=True)
    return (mid.x, mid.y), piece.length / 2


def cut_leg(leg, cuts):
    """Horizontal cuts → (bumper part above the first cut, [segments], {pivot: (x, y, r)})."""
    pivots, segs = {}, []
    for name, y in cuts:
        (mx, my), half = chord(leg, (200 if name in ('elbow', 'knee', 'fore-fetlock') else 520, y), (1, 0))
        pivots[name] = (mx, my, half + CAP_PAD)
    ys = [y for _, y in cuts] + [1e4]
    for i, (name, y) in enumerate(cuts):
        band = Polygon([(-1e4, y), (1e4, y), (1e4, ys[i + 1]), (-1e4, ys[i + 1])])
        px, py, r = pivots[name]
        segs.append(unary_union([leg.intersection(band), Point(px, py).buffer(r, 64)]))
    top = leg.intersection(Polygon([(-1e4, -1e4), (1e4, -1e4), (1e4, cuts[0][1]), (-1e4, cuts[0][1])]))
    return top, segs, pivots


def d_of(geom):
    """Shapely geometry → SVG path data (simplified, 0.1u precision)."""
    geom = geom.simplify(SIMPLIFY, preserve_topology=True)
    out = []
    for poly in getattr(geom, 'geoms', [geom]):
        if poly.is_empty or poly.geom_type != 'Polygon':
            continue
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)[:-1]
            out.append('M' + ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts) + 'Z')
    return ''.join(out)


# ── Tail warps ──────────────────────────────────────────────────────────────
def smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def warp_tail(d, bends):
    """Bend the hanging strand about the dock; the rump mass (inside the barrel)
    stays put. `bends` = [(degrees, curl exponent)], summed — higher exponent
    puts the bend toward the tip. Applied to control points so the warped tail
    stays a smooth Bezier path, not a polygon."""
    def f(pt):
        x, y = pt.x, pt.y
        s = math.hypot(x - DOCK[0], y - DOCK[1])
        w = smoothstep(544, 562, x)
        a = sum(deg * min(1.0, s / 170) ** k for deg, k in bends) * w
        c, sn = math.cos(math.radians(a)), math.sin(math.radians(a))
        dx, dy = x - DOCK[0], y - DOCK[1]
        pt.x, pt.y = DOCK[0] + dx * c - dy * sn, DOCK[1] + dx * sn + dy * c
    p = Path(d)
    for seg in p.segments():
        for attr in ('start', 'control1', 'control2', 'control', 'end'):
            q = getattr(seg, attr, None)
            if q is not None:
                f(q)
    return p.d()


TAILS = [  # (layer name, bends, visible) — positive = tail swings toward the head
    ('tail-hang', [], True),
    ('tail-swish-fwd', [(30, 1.7)], False),
    ('tail-swish-back', [(-32, 1.3)], False),
    ('tail-lifted', [(-62, 0.45), (20, 3.0)], False),
]

FILLS = {  # placeholder tints so piece boundaries show in Illustrator; the harness recolours to coat
    'bumper-front': '#b8905e', 'bumper-hind': '#b8905e', 'barrel': '#c9a676',
    'fore-forearm': '#9a6a3c', 'fore-cannon': '#83552c', 'fore-hoof': '#5e3c1e',
    'hind-gaskin': '#9a6a3c', 'hind-cannon': '#83552c', 'hind-hoof': '#5e3c1e',
    'neck': '#a87a48', 'head': '#8e6234', 'tail': '#735030',
}


def main():
    src = open(SPRITE).read()
    head_d = re.search(r'<g id="hz-head">.*?<path fill="currentColor" d="([^"]+)"', src, re.S).group(1)
    head = to_geom(head_d)
    lff, lfn = to_geom(sprite_path(src, 'hz-lff')), to_geom(sprite_path(src, 'hz-lfn'))
    lhn, lhf = to_geom(sprite_path(src, 'hz-lhn')), to_geom(sprite_path(src, 'hz-lhf'))
    tail_d = sprite_path(src, 'hz-tail')

    f_top, f_segs, f_pv = cut_leg(lff, FORE_CUTS)
    h_top, h_segs, h_pv = cut_leg(lhn, HIND_CUTS)
    (efx, efy), _ = chord(lfn, (200, FORE_CUTS[0][1]), (1, 0))
    (sfx, sfy), _ = chord(lhf, (480, HIND_CUTS[0][1]), (1, 0))

    (pcx, pcy), p_half = chord(head, *POLL_CUT)
    (wcx, wcy), w_half = chord(head, *WITHERS_CUT)
    w_r = CAP_OVERRIDE.get('withers', w_half + CAP_PAD)
    poll, withers = (pcx, pcy, p_half + CAP_PAD), (wcx, wcy, w_r)
    head_side = halfplane((pcx, pcy), POLL_CUT[1], MUZZLE)
    neck_side = halfplane((wcx, wcy), WITHERS_CUT[1], (pcx, pcy))
    body_side = halfplane((wcx, wcy), WITHERS_CUT[1], (400, 200))
    head_seg = unary_union([head.intersection(head_side), Point(pcx, pcy).buffer(poll[2], 64)])
    # Root zone = the band within one cap-radius past the withers cut. Where the
    # cap doesn't reach it, it's static (→ bumper), so the rotating neck's root
    # is exactly its round cap and never swings a corner out of the chest.
    wd = WITHERS_CUT[1]
    nx, ny = -wd[1] / math.hypot(*wd), wd[0] / math.hypot(*wd)
    if (pcx - wcx) * nx + (pcy - wcy) * ny < 0:
        nx, ny = -nx, -ny
    beyond = halfplane((wcx + nx * w_r, wcy + ny * w_r), wd, (pcx, pcy))
    disc = Point(wcx, wcy).buffer(w_r, 64)
    neck_region = head.difference(head_side).intersection(neck_side)
    neck_seg = unary_union([neck_region.intersection(beyond), disc])
    bumper_front = unary_union([head.intersection(body_side),
                                neck_region.difference(beyond).difference(disc), f_top])

    pivots = {**f_pv, **h_pv, 'withers': withers, 'poll': poll,
              'elbow-far': (efx, efy, 0), 'stifle-far': (sfx, sfy, 0), 'dock': (*DOCK, 0)}

    eye = ('<ellipse id="nostril" cx="47" cy="99" rx="6" ry="5" fill="#140d05"/>',
           '<ellipse id="eye-white" cx="84" cy="51" rx="10" ry="9" fill="#f3ecdb"/>',
           '<circle id="eye-pupil" cx="84" cy="51" r="4.4" fill="#140d05"/>')

    def g(name, d, fill, hidden=False):
        vis = ' display="none"' if hidden else ''
        return f'  <g id="{name}"{vis}>\n    <path fill="{fill}" d="{d}"/>\n  </g>'

    L = []
    L.append(HEADER.format(ground=GROUND, **{k.replace('-', '_'): f'({x:.1f},{y:.1f})'
                                             for k, (x, y, _) in pivots.items()}))
    L.append(GUIDES.format(ground=GROUND))
    L.append('  <g id="REF-2.4" display="none" fill="none" stroke="#c0392b" stroke-width=".8">\n'
             + ''.join(f'    <path d="{d_of(x)}"/>\n' for x in (head, lff, lfn, lhn, lhf, to_geom(tail_d)))
             + '  </g>')
    for name, bends, vis in TAILS:
        L.append(f'  <g id="{name}"{"" if vis else " display=\"none\""}>\n'
                 f'    <path fill="{FILLS["tail"]}" d="{warp_tail(tail_d, bends) if bends else tail_d}"/>\n  </g>')
    L.append(f'  <g id="barrel">\n    <rect fill="{FILLS["barrel"]}" x="150" y="110" width="400" height="100"/>\n  </g>')
    L.append(g('bumper-hind', d_of(h_top), FILLS['bumper-hind']))
    L.append(g('bumper-front', d_of(bumper_front), FILLS['bumper-front']))
    for name, seg in zip(('hind-gaskin', 'hind-cannon', 'hind-hoof'), h_segs):
        L.append(g(name, d_of(seg), FILLS[name]))
    for name, seg in zip(('fore-forearm', 'fore-cannon', 'fore-hoof'), f_segs):
        L.append(g(name, d_of(seg), FILLS[name]))
    L.append(g('neck', d_of(neck_seg), FILLS['neck']))
    L.append(f'  <g id="head">\n    {eye[0]}\n    <path fill="{FILLS["head"]}" d="{d_of(head_seg)}"/>\n'
             f'    {eye[1]}\n    {eye[2]}\n  </g>')
    pv = []
    for name, (x, y, r) in pivots.items():
        ring = f' data-cap="{r:.1f}"' if r else ''
        pv.append(f'    <circle id="pv-{name}" cx="{x:.1f}" cy="{y:.1f}" r="3.5"{ring} fill="#e0218a" stroke="#fff" stroke-width="1"/>')
    L.append('  <g id="PIVOTS">\n' + '\n'.join(pv) + '\n  </g>')
    L.append('</svg>')
    svg = '\n'.join(L) + '\n'
    with open(OUT, 'w') as fh:
        fh.write(svg)
    refresh_harness(svg, src)
    print(f'wrote {OUT}; refreshed the built-in copies in {HARNESS}', file=sys.stderr)


def refresh_harness(template_svg, sprite_src):
    """Re-embed the template, Clover's walk frames and the production sprite in
    the harness, so it keeps working as a single file opened from disk."""
    try:
        with open(HARNESS) as fh:
            h = fh.read()
    except FileNotFoundError:
        return
    defs = re.sub(r'\{#.*?#\}', '', re.search(r'<defs>(.*?)</defs>', sprite_src, re.S).group(1), flags=re.S)
    prod = f'<svg id="prod-sprite" width="0" height="0" style="position:absolute" aria-hidden="true"><defs>{defs}</defs></svg>'
    frames = {}
    with open(WALK_REF) as fh:
        for m in re.finditer(r'<(?:polygon|path) id="_x3(\d)_\d?"[^>]*?/>', fh.read()):
            frames.setdefault(m.group(1), []).append(re.sub(r' (?:id|data-name)="[^"]*"', '', m.group(0)))
    walk = ('<script type="text/plain" id="embed-walk">'
            + ''.join(f'<g data-frame="{k}">{"".join(v)}</g>' for k, v in sorted(frames.items())) + '</script>')
    tmpl = f'<script type="text/plain" id="embed-template">\n{template_svg}</script>'
    for key, content in (('PROD', prod), ('WALK', walk), ('TEMPLATE', tmpl)):
        h = re.sub(rf'<!--@{key}:begin-->.*?<!--@{key}:end-->',
                   lambda _m, k=key, c=content: f'<!--@{k}:begin-->{c}<!--@{k}:end-->', h, flags=re.S)
    with open(HARNESS, 'w') as fh:
        fh.write(h)


HEADER = '''<?xml version="1.0" encoding="UTF-8"?>
<!--
  poet.horse — POSABLE HORSE PARTS TEMPLATE (Phase 2.5.1 design sprint)
  =====================================================================
  Generated by prototypes/horse-parts-cut.py from the live 2.4 horse, so the
  neutral pose IS today's horse. Restyle the pieces over this geometry, export,
  and drop the SVG onto prototypes/horse-posing-harness.html to see it posed.

  COORDINATE FRAME (same as 2.4; SVG user units, y down):
    back line y=110 · belly y=210 · GROUND y={ground} (one number — hooves land here)
    front seam x=150 · rear seam x=550 · barrel x150..550 stretches, keep it flat

  THE PIECES (one group each — keep these names; Illustrator "Layer Names" IDs):
    bumper-front   static — chest + shoulder; hides the elbow + neck-root joints
    bumper-hind    static — haunch; hides the stifle joint
    fore-forearm   pivots at pv-elbow           fore-cannon  at pv-knee
    fore-hoof      pivots at pv-fore-fetlock    (pastern + hoof)
    hind-gaskin    pivots at pv-stifle          hind-cannon  at pv-hock
    hind-hoof      pivots at pv-hind-fetlock    (pastern + hoof)
    neck           pivots at pv-withers         head         at pv-poll
    tail-hang / tail-swish-fwd / tail-swish-back / tail-lifted — 4 hand-drawn
                   positions, NOT posable; only tail-hang is visible
    barrel         the stretchy rect — leave it alone
  One leg set serves all four legs: the far legs are the same pieces, moved to
  pv-elbow-far / pv-stifle-far and shaded darker in code.

  RULES FOR RESTYLING:
   1. The PIVOTS are the contract. Keep each piece's joint end round and
      centred on its pivot dot — the round cap is what keeps the silhouette in
      one piece at every angle. data-cap on each pivot = the current cap radius.
      You MAY move a pivot; the harness reads them from this file.
   2. A piece may overlap its neighbours freely — overlap is how it merges.
   3. Flat fill, any colour: the harness recolours everything to the coat.
      Exception: anything whose name starts eye- or nostril- keeps its colour.
   4. Hooves: the neutral hoof bottom should sit on the GROUND line.
   5. Don't rename groups. Extra groups are ignored; missing ones are reported.

  Pivots as generated (art units):
    elbow {elbow}  knee {knee}  fore-fetlock {fore_fetlock}
    stifle {stifle}  hock {hock}  hind-fetlock {hind_fetlock}
    withers {withers}  poll {poll}
-->
<svg id="horse-parts-template" xmlns="http://www.w3.org/2000/svg" width="680" height="360" viewBox="0 0 680 360">'''

GUIDES = '''  <g id="GUIDES" opacity=".9">
    <line x1="0" y1="110" x2="680" y2="110" stroke="#b9533a" stroke-width=".75" stroke-dasharray="5 4"/>
    <line x1="0" y1="210" x2="680" y2="210" stroke="#b9533a" stroke-width=".75" stroke-dasharray="5 4"/>
    <line id="ground-line" x1="0" y1="{ground}" x2="680" y2="{ground}" stroke="#2e8b57" stroke-width="1"/>
    <line x1="150" y1="92" x2="150" y2="300" stroke="#185fa5" stroke-width=".75" stroke-dasharray="4 3"/>
    <line x1="550" y1="92" x2="550" y2="300" stroke="#185fa5" stroke-width=".75" stroke-dasharray="4 3"/>
    <text x="6" y="106" font-family="sans-serif" font-size="9" fill="#8a5a3a">y110 back</text>
    <text x="6" y="206" font-family="sans-serif" font-size="9" fill="#8a5a3a">y210 belly</text>
    <text x="6" y="{ground}" dy="-3" font-family="sans-serif" font-size="9" fill="#2e8b57">y{ground} ground</text>
  </g>'''

if __name__ == '__main__':
    main()
