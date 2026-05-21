# Spec — Phases 1.14 + 1.15 + 1.19

Three independent features shipped together. Each can be reviewed/reverted independently.

---

## 1.14 — Report button + report queue

### Goal
Users (logged-in or anonymous) can flag a poem for admin review. Admin sees a queue and can action or dismiss each report.

### Schema
`reports` table already exists in schema.sql. No migration needed.

### Report form (poem permalink)
- "Report poem" button in the poem footer — always visible (logged-in and logged-out)
- Opens a small inline modal/form with:
  - Reason textarea (required, max 500 chars)
  - Submit button — calls `POST /poem/<short_code>/report`
  - Cancel button dismisses
- Logged-out: report is created with `reporter_user_id = NULL` and `reporter_ip` set from `request.remote_addr`
- Rate limiting: anonymous reporters limited to 3 reports per IP per hour (in-memory check via existing Flask-Limiter setup from 1.17)
- Success: inline "Thank you — this poem has been reported." message; no redirect

### Backend routes
- `POST /poem/<short_code>/report` — create a report
  - Body: `{reason: "..."}` (form or JSON)
  - Inserts into `reports(target_type='poem', target_id=poem.id, ...)`
  - Returns 200 or redirects; on success shows confirmation
- `GET /admin/reports` — admin-only queue, ordered by created_at DESC
  - Filters: `?status=pending` (default), `?status=actioned`, `?status=dismissed`, `?status=all`
  - Shows: reason, poem link (title or short_code), reporter (name if logged-in, else "anonymous + ip"), created_at
- `POST /admin/report/<int:id>/action` — mark as `actioned` or `dismissed`
  - Body: `{action: "actioned"|"dismissed"}`
  - Sets `status`, `resolved_at`, `resolved_by`

### Scope limits
- Only `target_type='poem'` for now. Display name / slug / tag reporting is future work.
- No email notifications.
- No duplicate detection (same user reporting same poem twice is fine for now).

---

## 1.15 — Poet profile `/u/<slug>`

### Goal
Public profile page shows a poet's published poems, their bio poem (if set), links, and joined date. Logged-in users can edit their own profile and set a bio poem.

### Schema migration
Add column to `users`:
```sql
ALTER TABLE users ADD COLUMN bio_poem_id INTEGER REFERENCES poems(id) ON DELETE SET NULL;
```

### Public profile page `/u/<slug>`

Sections (in order):
1. **Bio poem** (if `bio_poem_id` is set and poem is `published`) — rendered as a small poem block using the pasture renderer. On the user's own profile, shows an "Edit Bio" button even if no bio is set (opens bio picker).
2. **Poems list** — all `published` poems by this user, newest first. Each shows title (or first horse names if no title), published_at, short_code link. Simple paginated list, no fancy filter.
3. **Links** — `links_json` rendered as a list of labeled external links (open in new tab). If empty, section is hidden (shown as empty edit target for own profile).
4. **Joined date** — "Joined [date]".

Own-profile affordances (shown only when `current_user.id == poet.id`):
- "Edit profile" link → `/me/profile`
- "Edit Bio" button on bio section → opens bio picker modal (inline on page)

### Bio picker modal
- Only shown on the user's own profile page
- Lists all user's poems (published + submitted), newest first
- Published: selectable immediately
- Submitted (pending review): selectable with inline warning "This poem is pending review and won't appear as your bio until it's approved."
- Draft status poems: not shown in picker
- Current bio (if any) shown with "Currently set" indicator
- "Remove bio" option to clear `bio_poem_id`
- On select: `POST /me/profile/bio {poem_id: N}` → 200, refresh bio section

### `/me/profile` — edit profile
- Form fields:
  - Display name (text, max 80 chars)
  - External links: list of `{label, url}` pairs from `links_json` — add/remove rows
- Save: `POST /me/profile/save`
- Success: flash + redirect back to `/me/profile`

### `/me/published`
Redirect to `/u/<current_user.slug>`. Not a separate list page (the profile is the canonical published poems view).

### Backend routes
- `GET /u/<slug>` — full profile (rewrite stub)
- `GET /me/profile` — edit profile form
- `POST /me/profile/save` — update display_name + links_json
- `POST /me/profile/bio` — set or clear bio_poem_id
- `GET /me/published` — redirect to profile

### DB helpers (db/users.py)
- `update_profile(user_id, display_name, links)` — write display_name + links_json
- `set_bio_poem(user_id, poem_id_or_none)` — write bio_poem_id
- `get_user_published_poems(user_id)` — list of published poems by this user
- `get_user_poems_for_bio_picker(user_id)` — published + submitted poems

---

## 1.19 — Save (Blue Ribbon) + Pasture collections

### Goal
Build out the three collection pages: saved horses, saved poems, pasture horses. Add a ribbon save button on poem permalinks.

### Schema migration
New table for poem saves:
```sql
CREATE TABLE IF NOT EXISTS saved_poems (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    poem_id   INTEGER NOT NULL REFERENCES poems(id) ON DELETE CASCADE,
    saved_at  REAL    NOT NULL,
    PRIMARY KEY (user_id, poem_id)
);
CREATE INDEX IF NOT EXISTS idx_saved_poems_user ON saved_poems(user_id, saved_at DESC);
```

### Poem ribbon button
- Location: poem footer (alongside existing copy/export buttons)
- Blue ribbon emoji (🎀) or ribbon SVG; accessible label "Save poem"
- Logged-in: toggles saved state via `POST /poem/<short_code>/save`; updates aria-pressed + visual state
- Logged-out: clicking prompts sign-in (same pattern as horse popover sign-in prompt)
- On page load: fetch saved state from new `/poem/<short_code>/state` endpoint if logged in

### `/me/saved-poems`
- Saved poems, newest-first
- Each: title, poet attribution, saved_at, link to permalink
- "Remove" button to unsave

### `/me/saved-horses`
- Saved (ribbon) horses, newest-first
- Each: display name, link to PedigreeQuery URL, saved_at
- "Remove" button via `/horse/save` (toggle)

### `/me/pasture`
- Pasture horses, newest-first
- Each: display name, PQ link, added_at
- "Remove" button (new `DELETE /me/pasture/remove` endpoint)

### Backend routes
- `POST /poem/<short_code>/save` — toggle saved poem (requires login, returns `{saved: bool}`)
- `GET /poem/<short_code>/state` — return `{saved: bool}` for logged-in user (logged-out: `{saved: false}`)
- `GET /me/saved-poems` — list page (replace coming_soon)
- `GET /me/saved-horses` — list page (replace coming_soon)
- `GET /me/pasture` — list page (replace coming_soon)
- `POST /me/pasture/remove` — remove a horse from pasture by name

### DB helpers
New `db/saved_poems.py`:
- `toggle_saved_poem(user_id, poem_id) -> {saved: bool}`
- `list_saved_poems(user_id) -> list[dict]` — includes poem fields needed for display
- `is_poem_saved(user_id, poem_id) -> bool`

Add to `db/pasture.py`:
- `remove_from_pasture(user_id, name) -> bool`

---

## Out of scope this phase
- Public `/pasture` landing page (stays as coming_soon)
- Report targets other than poems (display_name, slug, tag)
- Following / follower graph
- Poem saves public aggregate count display
