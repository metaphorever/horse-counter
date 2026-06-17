# Phase 2.3 — Crosspost composition & tagging (Bluesky body + both-platform tags)

**Model:** Opus · **Effort:** high
**Depends on:** 2.2 (Bluesky connector, live-verified 2026-06-16)
**Status:** spec — awaiting Clover confirmation before build

Two features sharing one new data dependency — the poem's site tags carried onto
the crosspost item (`tags_for_poem`, [db/tags.py:207](../db/tags.py)):
**(A)** Bluesky post composition (sample body + discoverability hashtags + `sex`
self-label); **(B)** Tumblr site-tag crossposting (the poet's own tags, dropped
today). Scoped together because both consume the same `get_pending()` change;
doing them apart would touch that query twice.

---

## Problem

A Bluesky crosspost today (`_build_bluesky_post`, [app.py:2684](../app.py)) is a
single hook line plus a link card — **no poem body, no hashtags**:

```
"Title" a poem of 7 horses by Author
[ card → poet.horse/p/abc123 ]
```

Two gaps:

1. **No poem in the post.** Many poems are short enough to fit Bluesky's 300
   limit whole; longer ones could show a sample. Right now readers see zero
   poem unless they click through.
2. **No discoverability signal.** Tumblr posts carry boilerplate tags; Bluesky
   posts carry nothing, so the account is invisible to search and community
   feeds — the only discovery surfaces that work for a zero-follower account.

The link card is a **separate record field and does not count against the 300**,
so the entire text budget is currently unused. Adding a sample body + tags is
purely additive.

3. **Tumblr drops the poet's own tags.** `_build_crosspost`
   ([app.py:2650](../app.py)) tags a Tumblr poem with only `build_poem_tags`
   boilerplate — the poet's site tags (poem-type, theme, linguistic features,
   content warnings) never reach Tumblr. They should sit between the identity
   tags and the trailing boilerplate.

---

## Research findings (2026-06-17, Bluesky public API)

- **Discovery on Bluesky is not follower-gated.** Reach comes from search,
  hashtag feeds, and custom feed generators — all of which surface a brand-new
  account from its first post.
- **The horse world is fragmented by sub-interest.** `#horseracing` is active
  but skews industry/betting/stats; `#horses` is the affection/art crowd —
  the better vibe match for these poems even though the horses are racehorses
  (Clover's call).
- **The largest poetry feed is text-based.** "Poetry" (497 likes) scans post
  text for "poem/poet/poetry"; our header contains "poem", so we land there
  **for free, regardless of tags**. This frees the tag budget for horse
  targeting.
- **Micropoetry feed (110 likes)** keys on form tags (`#micropoetry`,
  `#micropoem`, `#haiku`, …). No canonical length threshold exists — the genre
  is "fits in one short post."
- **Hashtags require facets.** Plain `#text` posted via the API is *not* a
  working tappable/indexable tag; the tag facet must be built explicitly
  (`atproto` `client_utils.TextBuilder`).

---

## Decisions (resolved with Clover)

1. **Permalink stays in the card only** — no in-text URL. Frees ~25–30 chars
   for more poem; the card is the funnel-to-site path.
2. **Sample body, whole-horse truncation.** Fill poem lines greedily; never cut
   mid-horse-name. If the poem doesn't fully fit, truncate at a horse boundary
   (the last shown line may end the poem partway) and append a `[…]` marker.
3. **Budget to 290, not 300.** Bluesky's limit is 300 *graphemes*; `len()`
   counts codepoints. Identical for Latin horse names, so a 10-char safety
   margin covers the gap without a grapheme dependency (rule 10).
4. **Tags win.** Tags are reserved in the overhead before poem lines fill, so a
   tagged poem shows one fewer line rather than dropping a tag.
5. **Tag set (tunable constant):**
   - Base: `#poetry` · `#horses` · `#PoetHorse`
   - **Micropoetry swap:** full poem body ≤ **140 chars** → `#micropoetry`
     *replaces* `#poetry` (3 tags either way). Truncated poems are never
     micropoetry, so the swap only fires on short, fully-fitting poems.
   - Casing is cosmetic (case-insensitive matching); PascalCase for legibility.
6. **Content self-label:** site `sex` flag → Bluesky **`sexual`** self-label
   (suggestive, no-image). Not `porn` (image-oriented). Rides on the record at
   zero character cost. No other site tag maps to Bluesky's label vocabulary.
   This is a safety net under Clover's manual final-say, not a posting gate.
7. **Freebie:** set `langs=['en']` on the post. *(Card alt text was planned but
   dropped — AT Protocol external/link cards have no `alt` field; only image
   embeds do. The card's title + description already serve that role. Alt text
   returns with image cards, which are out of scope/Playwright.)*

---

## Composition algorithm

Build order (all char counts in the ~290 budget):

1. **Header** — reuse the existing hook:
   `"{title}" a poem of {N} horse{s} by {author}` (title/author clauses drop
   when absent). One blank line follows.
2. **Tags** — compute the 3-tag set; reserve its rendered length (tags + joining
   spaces) as committed overhead. Tags render on their own trailing line.
3. **Remaining budget** = `290 − len(header) − len("\n\n") − len(tag line) −
   len("\n") − (len("[…]") if truncated)`.
4. **Fill poem lines** greedily, joining with `\n`. A line is the horse
   `display` values space-joined (per `build_poem_html`, [poetry.py:365](../poetry.py)).
   Stop before the line that would overflow.
5. **Truncation marker** — if any line was dropped, append `[…]`.
6. **Degenerate case** — if even the first line won't fit whole, cut *within*
   that line at a horse boundary (drop trailing names until it fits), append
   `[…]`. Body is never empty when the poem has at least one horse.
7. **Facets** — render the whole text via `TextBuilder` so the tags are real
   tag facets, not plain text.

Card (`embed`) is unchanged: title + horse-name description + permalink. (Link
cards have no alt-text field — see decision 7.)

---

## Tag construction

```
BASE_TAGS      = ['horses', 'PoetHorse']          # always
POETRY_TAG     = 'poetry'
MICRO_TAG      = 'micropoetry'
MICRO_CUTOFF   = 140                               # chars of full poem body
```

- `poetry` vs `micropoetry` chosen by full-body length (pre-truncation).
- Site tags are **not** mapped to reach tags in v1 (Clover: none map cleanly).
  The constant is the single source of truth; revisit after living on the
  platform.
- Sanitize defensively even though the set is fixed: strip whitespace/punct,
  drop empties, dedup, cap at 5.

---

## Content labels

```
SITE_LABEL_MAP = {'sex': 'sexual'}                 # site CW slug → bsky self-label
```

The site stores content warnings as tags in the `content-warnings` category;
the authoritative slug is **`sex`** (per `db/seed.py` — `tools/seed_tags.py`'s
`cw-sex` is stale). Applied as a `com.atproto.label.defs#selfLabels` value on
the post record. Independent of text; costs no characters.

**Shared plumbing (serves both Bluesky labels and Tumblr tags):**
`get_pending()` in `db/crosspost.py` currently selects poem columns but **no
tags**. Extend it to attach `tags_for_poem(poem_id)` ([db/tags.py:207](../db/tags.py))
onto each item as `item['tags']` — the full approved tag list with `slug`,
`label`, `cat_slug`, `behavior`, `admin_only`. Bluesky consumes only the
`content-warnings` rows (→ self-label); Tumblr consumes all non-admin rows
(→ tag list). One query change, both consumers. This is the only
data-adjacent change in the phase.

---

## Tumblr site-tag crossposting

Splice the poet's site tags into the Tumblr tag list, between the identity block
and the trailing boilerplate.

- **Source:** `item['tags']` (the shared plumbing above). Exclude `admin_only`
  categories — internal classification, not public tags.
- **Render:** each tag as `label.lower()` (readable spaces: `free verse`,
  `internal rhyme`, `drugs and alcohol` — not the hyphenated slug). Tags in the
  `content-warnings` category get a `cw ` prefix → `cw death`, `cw self-harm`.
- **Order:** by category `sort_order` (poem-type → theme → linguistic →
  content-warnings), which is how `tags_for_poem` already returns them.
- **Insertion point:** immediately **before `counting-horses`** in the
  `build_poem_tags` output. Dedup against existing tags.

Resulting order (Clover's example):

```
horse poetry, how many horses?, 16 horses, 100% horse, user submission,
poetry, text post, [haiku, love, loss, cw death, cw self-harm],
counting-horses, gimmick account, horseblr
```

Implementation: a small helper turns `item['tags']` into the ordered tag-string
fragment, spliced in `_build_crosspost` ([app.py:2650](../app.py)). Bluesky is
unaffected — it still maps only the `content-warnings` category to a self-label
and does **not** carry site tags as reach hashtags (per the v1 decision above).

### Decisions baked in (low-stakes — correct at review)

- `cw ` prefix with a space, consistently (`cw self-harm`, reading the bare
  `cwself-harm` example as a typo).
- `label.lower()` over slug, for readable multi-word tags.
- All non-admin categories flow through (incl. linguistic-features).

---

## Open question (Clover confirms live, not blocking)

- **Final tag list.** Ships with `#poetry / #horses / #PoetHorse` (+ micropoetry
  swap). Clover watches the live feeds for a week and tunes the constant —
  candidates to evaluate: courting Equestrian Blueskies / EquestrianBSKY (tag
  convention unconfirmed), `#micropoetry` cutoff value. No redeploy-shaped
  decisions; all constants.

---

## Test plan (live site — preview pane can't post)

1. **Short poem (fits whole):** body shows entire poem, no `[…]`, 3 tags
   tappable, card present. Verify it appears in `#horses` search.
2. **Long poem (truncates):** body shows whole horses up to budget, ends with
   `[…]`, `#poetry` (not micropoetry), under 300 graphemes.
3. **Micropoetry (≤140 body):** carries `#micropoetry`, not `#poetry`.
4. **Degenerate (one giant first line):** body cut at a horse boundary, non-empty.
5. **Untitled / anonymous:** header clauses drop cleanly.
6. **Sex-flagged poem:** post carries the `sexual` self-label (check via the
   post's moderation state).
7. **Grapheme margin:** a poem engineered near 290 chars still posts (no
   length rejection).
8. **Tumblr site tags:** a poem with poem-type + theme + CW tags crossposts to
   Tumblr with them spliced before `counting-horses`, CW-prefixed `cw `,
   multi-word tags rendered with spaces.
9. **Tumblr no-tags poem:** an untagged poem produces the original boilerplate
   list, no empty/stray tags.

---

## Out of scope

- Image cards (Playwright work — separate track).
- Mapping arbitrary site tags → reach tags.
- Threading long poems across multiple posts.
- Automated content-moderation beyond the single `sex` → `sexual` mapping.
