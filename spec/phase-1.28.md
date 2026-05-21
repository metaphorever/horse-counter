# Phase 1.28 — Draft polish: popover quick-create + editor auto-save redesign

**Model:** Sonnet · **Effort:** medium

---

## Problem

Phase 1.27 shipped a working draft system but two areas need rework before it's genuinely usable:

1. **Popover (0-draft state)**: Hiding the draft section when the user has no drafts is a dead end. They need a way to start a new draft from the horse menu without navigating away.
2. **Editor explicit-save model**: "Save Draft" as a deliberate user action is wrong for this kind of tool. Auto-save is the right model; the UI should reflect that.

---

## Overrides

These decisions from prior phases are **explicitly superseded** by this spec:

| Overridden decision | Replacement |
|---|---|
| "Save Draft" explicit save button (1.27) | Auto-save for structural content; "Edit Details" for metadata only |
| 0-draft popover state hides the section (PR #39 bug fix, 2026-05-20) | Quick-create inline form replaces the hidden state |

---

## Design decisions (all resolved)

### 1. Popover — draft section

**0-draft state:** Show a quick-create form inline:

```
Add to Draft
  [___________________________] [+ New]
  (placeholder: "Draft title (optional)")
```

- "+ New" creates a new draft immediately, adds the horse to its stable, shows a toast: `Draft "TITLE" created.` (or `Draft "untitled" created.` if blank)
- No page navigation required

**1+-draft state:** Show the existing draft list (direct add as before). Below the list, a **collapsed** "Add to new draft" expander:

```
+ Add to new draft ▸
```

Clicking it expands the same inline quick-create form in-place. This keeps the primary action (add to existing draft) front-and-center and the secondary action (new draft) one click away.

---

### 2. Editor page load

**0 drafts:** Drop the user directly into a blank, auto-saving draft. No picker — minimum friction. A new blank draft is created automatically on first structural save (first horse added to stable or poem), named "untitled" until "Edit Details" is used.

**1+ drafts:** Before showing the compose area, display a draft picker:

```
What draft would you like to edit?

  ● Draft Title           3 horses  2h ago
  ○ Another Draft         1 horse   yesterday
  ─────────────────────────────────────────
  + New Empty Draft
```

- Drafts in recent-activity order (`updated_at DESC`)
- Selecting a draft loads its stable + poem lines into the compose area
- "New Empty Draft" drops into the 0-draft path (blank compose area, auto-save on first change)
- The picker is shown on page load when `?draft=<id>` is NOT in the URL. If `?draft=<id>` is present (e.g. from `/me/drafts` "Resume editing" link), skip the picker and load that draft directly.

---

### 3. Editor UI redesign

The old layout (Save Draft button floating somewhere near the post area) is replaced with:

```
┌──────────────────────────────────────────────────┐
│  [poem compose area — stable + poem lines]       │
└──────────────────────────────────────────────────┘
  Currently editing: DRAFT NAME          [Change Draft ▾]
──────────────────────────────────────────────────────
  [Clear Stable]  [Clear Poem]  [Edit Details]  [Post Poem]
```

**"Change Draft ▾"** — opens the draft picker as an overlay/dropdown (same component as page-load picker). Selecting a different draft saves the current one first (auto-save flush), then loads the new one.

**"Clear Stable"** — prompts:
```
This will remove all horses from the stable.
Where should they go?
  [Send to my pasture]   [Set these horses loose]   [Cancel]
```

**"Clear Poem"** — prompts:
```
This will remove all horses from the poem.
Where should they go?
  [Send to the stable]   [Send to my pasture]   [Set these horses loose]   [Cancel]
```

**"Edit Details"** — opens the existing modal (title, tags, attribution, author name/tumblr). On save, persists immediately; does NOT require any other action.

**"Post Poem"** — unchanged functionally; may be renamed if needed.

No renaming of functional behavior. Only the Save Draft button is removed; all existing modal fields and backend calls are preserved.

---

### 4. Auto-save model

| Trigger | Save timing |
|---|---|
| Horse added to stable | Immediate (no debounce) |
| Horse removed from stable | Immediate |
| Horse added to poem | Immediate |
| Horse removed from poem | Immediate |
| Horse repositioned within poem (drag) | Debounced ~5–10s |
| "Edit Details" modal save | Immediate |
| Tab close / page unload | Best-effort flush (existing auto-save is sufficient) |

**Anonymous users:** mirror server behavior — save immediately on add/remove to `horse-draft` localStorage key. Generous debounce on drag.

**Toast behavior:** no toast on auto-save (silent). Toast only on "Edit Details" save: `Draft "TITLE" saved.`

**Draft creation:** a new blank draft (id = null) is created on the server at the moment of the **first** immediate auto-save trigger (first horse added to stable or poem). Before that point, nothing is written to the DB. The `?draft=<id>` URL param is updated in-place with `history.replaceState` once the draft ID is known.

---

## Backend changes required

| Endpoint | Change |
|---|---|
| `GET /me/draft/get?id=<id>` | **New.** Returns full draft JSON: `{id, title, lines_json, stable_json, submitter_name, submitter_tumblr, inspired_by_text, inspired_by_url, tag_ids, created_at, updated_at}`. Used to load a draft into the editor. |
| `POST /me/draft/save` | Already exists. Called by auto-save on every immediate trigger. Ensure it creates a new draft if `draft_id` is null and returns the new ID. |
| `POST /me/draft/create` | May already exist from 1.27; confirm and use for popover quick-create. Should accept `{title, horse_name}` and return `{draft_id}`. |
| `GET /me/draft/list` | Already exists. Used by picker to populate draft list on page load. |

---

## Out of scope for this phase

- Draft sharing / collaboration
- Draft version history / undo
- Batch delete from `/me/drafts`
- Any visual redesign of chips or the compose area

---

## Testing holds (for session close)

Before the next phase starts, Clover verifies:

1. Horse menu with 0 drafts shows the quick-create form, and "+ New" creates a draft + adds the horse
2. Horse menu with 1+ drafts shows the list; "Add to new draft" expander works
3. Editor with 0 drafts loads a blank compose area, auto-saves on first horse add, URL updates with `?draft=<id>`
4. Editor with 1+ drafts shows the picker; selecting a draft loads its horses; "New Empty Draft" works
5. "Change Draft ▾" saves the current draft and loads the selected one
6. "Clear Stable" prompt shows correct destination options; horses go where indicated
7. "Clear Poem" prompt shows correct options including "Send to the stable"
8. "Edit Details" opens the modal with existing values pre-populated; saves metadata without clearing poem/stable
9. Auto-save is silent (no toast on every save); "Edit Details" save shows toast
10. Anonymous flow: localStorage draft updates on stable/poem changes without login
