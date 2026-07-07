# Phase 2.6 — Count search (shared-name search)

**Model:** Sonnet · **Effort:** medium *(small, contained backend surface — bump to Opus only if bundled with unrelated work)*
**Depends on:** nothing — builds on the existing Wildcard search path
**Status:** spec DRAFT pending Clover review
**Ships:** search the dictionary by *how many horses share a name*, on its own (`>8`) or combined with a name pattern (`*love*>8`), inside the existing Wildcard search box.

Origin: Clover user-suggestion (2026-07-06). "A search that finds names shared by
N horses — `8` shows names shared by exactly 8, `>8` shows names shared by more than 8."
Extended in the same session to the combined form: `*LOVE*>8` = the wildcard `*love*`
search restricted to names shared by more than 8 horses.

---

## Why this is cheap (the load-bearing facts)

Every horse name in `dictionary.horses` maps to a **list of registration dicts**; the
number we're searching on is just `len(registrations)`, and it is *already computed and
returned* as the `count` field on every search result (`poetry.py` `search_dictionary`,
line ~310). So:

- **No data-model change.** The number already exists on every chip.
- **No new UI mode.** It lives inside the existing Wildcard box — see the grammar below.

**The grammar is unambiguous because of a hard fact about the data**, verified against
all **2,123,231** normalized names (2026-07-06, full-dictionary scan):

- Names containing a digit `0-9`: **0**
- Names containing `<`, `>`, or `=`: **0**
- The entire character set across every name is **`a`–`z` and space** — nothing else.

So a trailing count-expression can *never* collide with a name. This is the whole
reason the feature is safe to overload onto the search box, and it must be re-checked
if the dictionary's normalization ever changes (see Safeguards).

---

## The grammar

Parse the query by **peeling a trailing count-expression off the end**:

```
COUNT_TAIL = /\s*(>=|<=|>|<|=)?\s*(\d+)\s*$/
```

Whatever precedes the matched tail is the **name pattern** (today's Wildcard grammar,
`_compile_search`). Cases:

| Input | Name part | Count filter | Meaning |
|---|---|---|---|
| `8` | — | `= 8` | names shared by exactly 8 horses |
| `>8` | — | `> 8` | names shared by more than 8 |
| `>=8` | — | `>= 8` | names shared by 8 or more |
| `*love*>8` | `*love*` | `> 8` | love-names shared by more than 8 |
| `star*>=10` | `star*` | `>= 10` | starts-with-"star", shared by 10+ |
| `*love*8` | `*love*` | `= 8` | (bare number still = exact; unambiguous) |
| `*love*` | `*love*` | — | today's behavior, untouched |
| `*>8`, `**>8` | — (wildcard-only) | `> 8` | name part is empty → pure count search |

**Operators supported in v1:** `=` (or bare number), `>`, `>=`.

**`<` and `<=` are deferred** — not because they're hard, but because they're
degenerate on this data: every "less than" query includes the count-1 bucket
(1,790,534 names, 84% of the dictionary), so `<5` matches ~2.05M names and returns
an arbitrary capped sample. Low value, easy to add later if a use emerges. If entered
in v1, treat as an invalid count expression (fall through to name search, which will
find nothing and hit the existing 3-char / no-results messaging).

---

## Safeguards

1. **Reject `=1` (and any predicate that resolves to "count == 1").** That's 84% of the
   dictionary and means "names nobody else shares" — useless as a result set and a
   1.79M-row collect. Return a friendly error via the existing `error` field:
   *"Every horse shares its name with at least itself — try 2 or more (e.g. `>8`)."*
   Concretely: reject `=1`, `1`. (With `<`/`<=` deferred, no other v1 operator can
   resolve to count-1-only.)

2. **The cap does the heavy lifting — order it deliberately.** Almost every count query
   exceeds `SEARCH_HARD_CAP = 2000` (you don't drop under 2000 total until ~`>=24`).
   Collect with `heapq.nlargest(SEARCH_HARD_CAP, ...)` keyed on **(count desc, name)** so
   a capped result keeps the *most-shared* names, not whichever the dict happened to
   iterate first. For `>=`/`>` this makes the cap feel intentional ("top 2000 most-shared").
   For exact `=N` every match is tied on count, so it falls to alphabetical — a
   deterministic 2000-name sample; label it as a sample in the results header (below).

3. **Count-first filter (perf + correctness).** In the scan loop, apply the O(1) count
   predicate *before* the regex. For combined queries this makes the search **faster than
   the plain wildcard** it's built on (measured: `*love*>8` ≈ 294 ms vs `*love*` ≈ 1280 ms
   on the full dictionary, because the regex only runs on the ~22k names that pass `>8`).

4. **3-char minimum applies to the name part only, after peeling the count.** When the
   name part is empty or wildcard-only, **skip** the name filter entirely rather than
   failing `_compile_search`'s 3-char check — that's how `>8` and `*>8` become pure
   count searches.

5. **The char-set guarantee is an invariant, not a coincidence.** The unambiguous parse
   depends on names never containing digits or `<>=`. If dictionary normalization ever
   changes to admit them, this grammar breaks. Add a one-line note at the parse site and
   in the dictionary-build docs.

---

## Result ordering & the header

- **Pure count query** (no name part): sort **count desc, then name**. Header reads e.g.
  *"Names shared by more than 8 horses — 120 shown"*, and when capped:
  *"…showing the 2000 most-shared (of many)."* For exact `=N`: *"Names shared by exactly 8
  horses — showing a sample of 2000"* when capped.
- **Combined query** (name + count): the name filter almost always drops the set below the
  cap, so sort by the **existing name-relevance order** (exact → prefix → alpha) — count is
  acting as a filter, not the sort key. Header reads e.g.
  *"`*love*`, shared by more than 8 — 120 results."* Cap selection (rare here) still uses
  the count-desc key from safeguard 2.

Result shape is unchanged (`{results, total, capped, query, error, mode}`; each result
`{name, display, url, count}`), so the existing chip renderer and pager need no changes.
The `mode` string carries the human-readable header text above (extend `_describe_mode`).

---

## Distribution (for reference — full scan 2026-07-06)

Exact-count spread and cumulative (`>=`) totals, to sanity-check the cap and the floor:

| N | exactly N | ≥ N (cumulative) |
|---:|---:|---:|
| 1 | 1,790,534 | 2,123,231 |
| 2 | 174,068 | 332,697 |
| 3 | 61,347 | 158,629 |
| 4 | 30,579 | 97,282 |
| 8 | 5,910 | 28,561 |
| 12 | 2,041 | 12,164 |
| 13 | 1,682 | 10,123 |
| 24 | 239 | 1,916 |

Reading: exact queries of `=13` and up return a **complete, uncapped** set; `>=24` and up
are uncapped cumulatively. Everything below trips the cap → safeguard 2 matters.

---

## Discoverability (non-negotiable — this dies without it)

The syntax is **completely undiscoverable** — nobody stumbles onto `*love*>8`. Agreed
with Clover (2026-07-06): the feature ships **with** worked examples in the search help,
or it's dead on arrival.

- **Help modal** (`templates/poetry.html`, the "? How it works" `<li>` at ~line 305):
  add a bullet with 2–3 live examples: `>8` (shared by more than 8), `*star*>20`
  (popular star-names), `=2` (shared by exactly 2). Make them clickable
  `suggest-search` links like the existing no-results suggestions (line ~730) so a click
  runs the search.
- **Placeholder / hint:** consider extending the Wildcard placeholder
  (`e.g. *dance* or dance *`) or the `search-mode` line to mention the count form once.
  Keep it light — one example, not a syntax dump.

---

## Scope

**In:** `poetry.py` — a parse helper (peel count tail → `(name_part, count_pred)`) and
the count-aware branch inside `search_dictionary` (reusing `_compile_search` for the name
part); `_describe_mode` extended for the new header strings; help-modal examples in
`templates/poetry.html`. The `/poetry/search` endpoint (`app.py` ~2020) is **untouched** —
same route, same 60/min rate limit, same JSON shape.

**Out:** no new endpoint, no new search toggle, no schema change, no `<`/`<=` operators,
no ranges (`3-8`) — note both as easy future extensions. Rhyme/Thesaurus/Short-names
modes untouched.

**Testing (live, per CLAUDE.md rule 14):** the gz dictionary is prod-only, so verify on
poet.horse (or staging) after deploy: `>8`, `>=24`, `=13`, `=2`, `*love*>8`, `*star*>20`,
`=1` (rejected with the friendly message), `*>8` (pure count), plain `*love*` (unchanged),
and the help-modal example links. Confirm the capped-sample header wording reads right on
a `=2` query.
