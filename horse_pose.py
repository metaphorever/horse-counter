"""
horse_pose.py — Phase 2.5.1 static pose variation for Fancy-view chips.

Every server-rendered chip gets a random standing pose (legs, head, tail) and a
random facing, fresh on each render. horse_svg() in templates/macros.html turns
h['pose'] into <use> refs into the baked sprite.

The pool is read from the sprite itself (templates/_horse_sprite.html, baked by
prototypes/horse-posing-harness.html): each pose there carries data-pool and
data-weight, so the server can only ever pick a pose the sprite really has, and
how often each one comes up is set in one place (re-bake, or edit data-weight).
"""

import os
import random
import re
import sys

_SPRITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', '_horse_sprite.html')
_ENTRY = re.compile(r'<g id="hz-(?:st|hd|tl)-([a-z0-9-]+)" data-pool="(stance|head|tail)" data-weight="([0-9.]+)"')

# The pose horse_svg() falls back to when a chip has none (e.g. the JS-rendered
# infinite pasture). Keep in step with the default in macros.html.
DEFAULT_POSE = {'stance': 'square', 'head': 'relaxed', 'tail': 'hang'}


def _load_pool(path: str = _SPRITE) -> dict:
    pool = {'stance': {}, 'head': {}, 'tail': {}}
    try:
        with open(path, encoding='utf-8') as f:
            for key, kind, weight in _ENTRY.findall(f.read()):
                pool[kind][key] = float(weight)
    except OSError as e:
        print(f'[horse_pose] could not read the sprite: {e}', file=sys.stderr)
    for kind, entries in pool.items():
        if not entries:
            print(f'[horse_pose] no {kind} poses in the sprite; every chip gets the default', file=sys.stderr)
    return pool


POOL = _load_pool()


def _pick(weights: dict, fallback: str) -> str:
    if not weights:
        return fallback
    keys = list(weights)
    return random.choices(keys, weights=[weights[k] for k in keys])[0]


def assign_pose(h: dict) -> None:
    """Give horse dict `h` a random standing pose and facing, in place."""
    h['pose'] = {kind: _pick(POOL[kind], DEFAULT_POSE[kind]) for kind in DEFAULT_POSE}
    h['rev'] = random.random() < 0.5
