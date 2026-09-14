#!/usr/bin/env python3
"""Phase 2.5.1 — lengthen the neck of Clover's parts art so Graze reaches the grass.

Clover picked "option 2" on 2026-09-14 (sessions/2026-09-14-phase-2.5.1-graze-neck.md):
  * pv-withers moves DROP down and BACK back, to the base of the neck, so the neck
    swings from low in the chest. The neck gets a round root disc there, bridged to
    the old disc; all of it sits inside the front bumper at neutral.
  * The visible neck grows STRETCH along its withers->poll axis. The crest keeps its
    withers end; everything past T1 on the axis rides with the head. The head and
    pv-poll slide out with it; the head is moved, not reshaped.
  * The front bumper's dome above the back line is squashed toward y=110 (DOME_KEEP)
    so the withers don't hump when the head drops.
Legs, tails, guides and hidden layers pass through untouched.

  python3 prototypes/horse-parts-neck.py IN.svg OUT.svg

Needs svgelements (scratch venv, same as horse-parts-cut.py). It refuses art whose
pv-withers has already moved, so it can't lengthen a neck twice.
"""
import math
import re
import sys

from svgelements import Close, CubicBezier, Line, Move, Path, QuadraticBezier

DROP, BACK = 25.0, 3.0      # new withers pivot = old + (BACK, DROP)
STRETCH = 20.0              # visible neck length added, art units
T0, T1 = 0.0, 72.0          # stretch ramp along the withers->poll axis (from the old withers)
DISC_R = 46.0               # neck root cap radius (unchanged)
BACK_LINE, DOME_KEEP = 110.0, 0.45   # bumper points above y=110 keep 45% of their height
GROUND, HEAD_WORLD = 344.5, -30.0    # for the printed graze check only
CAPS = {'elbow': 32.0, 'knee': 13.1, 'fore-fetlock': 11.0, 'stifle': 28.3, 'hock': 14.9,
        'hind-fetlock': 9.4, 'withers': DISC_R, 'poll': 40.5}  # Illustrator drops data-cap

HEADER = """<!--
  poet.horse — POSABLE HORSE PARTS, art pass 1 + long neck (Phase 2.5.1 design sprint)
  Clover's art pass (horse-parts-template-Edit.svg) run through horse-parts-neck.py:
    pv-withers {w_old} -> {w_new}  (the base of the neck; the neck swings from low in the chest)
    pv-poll    {p_old} -> {p_new}  (neck +{stretch:g}u; the head moved out with it, not reshaped)
    front bumper dome squashed toward the back line so grazing doesn't hump the withers
  Graze now reaches the grass. The ears sit {top:.0f}u above the artboard at neutral; that is expected.
  Same rules as horse-parts-template.svg: keep group names, keep joint ends round on their
  pivots, export with Object IDs = Layer Names, save under a new name.
-->
"""


def num(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


def pt(p):
    return f'{num(p[0])},{num(p[1])}'


def subpaths(d):
    subs, cur = [], None
    for seg in Path(d):
        if isinstance(seg, Move):
            cur = [seg]
            subs.append(cur)
        else:
            cur.append(seg)
    return subs


def ser(subs, fn):
    out = []
    for sub in subs:
        for seg in sub:
            if isinstance(seg, Move):
                out.append('M' + pt(fn(seg.end)))
            elif isinstance(seg, Close):
                out.append('Z')
            elif isinstance(seg, Line):
                out.append('L' + pt(fn(seg.end)))
            elif isinstance(seg, CubicBezier):
                out.append('C' + ' '.join(pt(fn(q)) for q in (seg.control1, seg.control2, seg.end)))
            elif isinstance(seg, QuadraticBezier):
                out.append('Q' + ' '.join(pt(fn(q)) for q in (seg.control, seg.end)))
            else:
                raise ValueError(f'unhandled path segment {type(seg).__name__}')
    return ''.join(out)


def sample(subs, fn, n=24):
    return [fn(seg.point(i / n)) for sub in subs for seg in sub if not isinstance(seg, Move) for i in range(n + 1)]


def rot(p, c, a):
    r = math.radians(a)
    x, y = p[0] - c[0], p[1] - c[1]
    return (c[0] + x * math.cos(r) - y * math.sin(r), c[1] + x * math.sin(r) + y * math.cos(r))


def inside(poly, p):
    x, y, hit = p[0], p[1], False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def main(src_path, out_path):
    src = open(src_path, encoding='utf-8').read()

    def pivot(name):
        m = re.search(r'<circle id="pv-%s" cx="([-\d.]+)" cy="([-\d.]+)"' % name, src)
        return float(m.group(1)), float(m.group(2))
    W, P = pivot('withers'), pivot('poll')
    if math.dist(W, (187.0, 144.7)) > 1:  # Illustrator strips the header comment, so check the pivot itself
        sys.exit(f"pv-withers is at {pt(W)}, not the cut template's 187,144.7: this art was already "
                 'lengthened. Run the script on the un-lengthened art.')
    L = math.dist(W, P)
    ux, uy = (P[0] - W[0]) / L, (P[1] - W[1]) / L
    Wn = (W[0] + BACK, W[1] + DROP)
    off = (STRETCH * ux, STRETCH * uy)
    Pn = (P[0] + off[0], P[1] + off[1])

    # ── neck: stretch the strip, keep the old disc, add bridge + new disc ──
    m = re.search(r'(<g id="neck">\s*<path d=")([^"]+)("( fill="[^"]+")?\s*/>)', src)
    neck_fill = m.group(4) or ''
    subs = subpaths(m.group(2))
    disc = [i for i, s in enumerate(subs)
            if all(abs(math.dist(q, W) - DISC_R) < 3 for q in sample([s], lambda p: (p.x, p.y), 4))]
    if len(disc) != 1:
        sys.exit(f'expected one round root disc (r={DISC_R}) in the neck, found {len(disc)}')

    def stretch(p):
        t = (p.x - W[0]) * ux + (p.y - W[1]) * uy
        s = min(1.0, max(0.0, (t - T0) / (T1 - T0)))
        return (p.x + STRETCH * s * ux, p.y + STRETCH * s * uy)
    ident = lambda p: (p.x, p.y)
    strip = [s for i, s in enumerate(subs) if i not in disc]
    neck_d = ser(strip, stretch) + ser([subs[disc[0]]], ident)
    nx, ny = -(Wn[1] - W[1]), Wn[0] - W[0]
    k = DISC_R / math.hypot(nx, ny)
    bridge = [(W[0] + nx * k, W[1] + ny * k), (Wn[0] + nx * k, Wn[1] + ny * k),
              (Wn[0] - nx * k, Wn[1] - ny * k), (W[0] - nx * k, W[1] - ny * k)]
    extra = (f'\n    <path d="M{"L".join(pt(q) for q in bridge)}Z"{neck_fill}/>'
             f'\n    <circle cx="{num(Wn[0])}" cy="{num(Wn[1])}" r="{num(DISC_R)}"{neck_fill}/>')
    src = src[:m.start()] + m.group(1) + neck_d + m.group(3) + extra + src[m.end():]

    # ── head: slide out with the poll ──
    hm = re.search(r'<g id="head">.*?</g>', src, re.S)
    head = hm.group(0)
    head_subs = []

    def move_path(mm):
        s = subpaths(mm.group(1))
        head_subs.extend(s)
        return ' d="' + ser(s, lambda p: (p.x + off[0], p.y + off[1])) + '"'
    head = re.sub(r'\sd="([^"]+)"', move_path, head)  # \s: don't match the tail of id="..."
    head = re.sub(r'cx="([-\d.]+)"', lambda mm: f'cx="{num(float(mm.group(1)) + off[0])}"', head)
    head = re.sub(r'cy="([-\d.]+)"', lambda mm: f'cy="{num(float(mm.group(1)) + off[1])}"', head)
    src = src[:hm.start()] + head + src[hm.end():]

    # ── front bumper: squash the dome toward the back line ──
    bm = re.search(r'(<g id="bumper-front">\s*<path d=")([^"]+)(")', src)
    squash = lambda p: (p.x, p.y if p.y >= BACK_LINE else BACK_LINE - (BACK_LINE - p.y) * DOME_KEEP)
    bsubs = subpaths(bm.group(2))
    src = src[:bm.start()] + bm.group(1) + ser(bsubs, squash) + bm.group(3) + src[bm.end():]

    # ── pivots ──
    for name, (x, y) in (('withers', Wn), ('poll', Pn)):
        src = re.sub(r'(<circle id="pv-%s" )cx="[-\d.]+" cy="[-\d.]+"' % name,
                     lambda mm: f'{mm.group(1)}cx="{num(x)}" cy="{num(y)}"', src)
    for name, r in CAPS.items():
        src = re.sub(r'(<circle id="pv-%s"(?![^>]*data-cap)[^>]*?) r="3.5"' % name,
                     lambda mm: f'{mm.group(1)} r="3.5" data-cap="{r}"', src)

    # ── checks, printed ──
    head_pts = [(q[0] + off[0], q[1] + off[1]) for q in sample(head_subs, lambda p: (p.x, p.y))]
    neck_pts = sample(strip, stretch)
    top = min(q[1] for q in head_pts + neck_pts)
    bump = sample(bsubs, squash, 40)
    corner_ok = inside(bump, (150.5, 110.5))
    graze = None
    for i in range(2601):
        a1 = -i * 0.05
        low = max((rot(rot(q, Pn, HEAD_WORLD - a1), Wn, a1) for q in head_pts), key=lambda q: q[1])
        if low[1] >= GROUND - 2:
            graze = (a1, HEAD_WORLD - a1, low[0])
            break

    src = src.replace('<svg ', HEADER.format(w_old=pt(W), w_new=pt(Wn), p_old=pt(P), p_new=pt(Pn),
                                             stretch=STRETCH, top=-top) + '<svg ', 1)
    open(out_path, 'w', encoding='utf-8').write(src)
    print(f'withers {pt(W)} -> {pt(Wn)}   poll {pt(P)} -> {pt(Pn)}   lever {L:.1f} -> {math.dist(Wn, Pn):.1f}u')
    print(f'neutral head/neck top y={top:.1f}   bumper top y={min(q[1] for q in bump):.1f}'
          f'   barrel corner covered by bumper: {corner_ok}')
    print('graze (head %g° world): ' % HEAD_WORLD +
          (f'withers {graze[0]:.1f}°, poll {graze[1]:.1f}°, muzzle x {graze[2]:.0f}' if graze else 'NOT REACHED'))
    print('wrote', out_path)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
