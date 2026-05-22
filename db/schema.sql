-- poet.horse — SQLite schema (initial)
--
-- All timestamps are stored as REAL (Unix epoch seconds, fractional ok).
-- All "_json" columns hold JSON text — read with json_extract or parse client-side.
-- Foreign keys are declared but require PRAGMA foreign_keys = ON at connect time.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Users ────────────────────────────────────────────────────────────────────
-- One row per signed-in user. Anonymous poems do not create a row here;
-- their authorship is captured by poems.author_display_name with author_user_id NULL.
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY,
    clerk_id            TEXT    NOT NULL UNIQUE,
    slug                TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    display_name        TEXT    NOT NULL,
    role                TEXT    NOT NULL DEFAULT 'user',     -- 'user' | 'admin'
    -- Moderation trust signal (Phase 1.3 scaffold). Acted on in Phase 1.13:
    --   'pending'  — default; poems go to the submission queue
    --   'trusted'  — auto-publish; tag suggestions auto-approve (admin can revoke)
    --   'flagged'  — extra scrutiny; flagged-horse-name guard applies, etc.
    trust_level         TEXT    NOT NULL DEFAULT 'pending',
    preferences_json    TEXT    NOT NULL DEFAULT '{}',
    flags_json          TEXT    NOT NULL DEFAULT '{}',       -- e.g. {"ad_free": true}
    -- Profile links — list of {"label": "Bluesky", "url": "https://..."} dicts.
    -- Surfaced on the user's profile page and as the attribution links on
    -- their poems. Order in the array is the display order.
    links_json          TEXT    NOT NULL DEFAULT '[]',
    -- Phase 1.15: poem chosen as profile bio. NULL = no bio set.
    -- Applied via ALTER TABLE migration on existing DBs (seed.py).
    bio_poem_id         INTEGER REFERENCES poems(id) ON DELETE SET NULL,
    joined_at           REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- ── Poems ────────────────────────────────────────────────────────────────────
-- lines_json shape: [[{"name": "...", "display": "...", "url": "..."}], ...]
--   Outer list = lines (one element per line break); inner list = horses on that line.
-- status: 'draft' | 'submitted' | 'published' | 'hidden' | 'rejected'
--
-- Authorship model:
--   * Logged-in poems → author_user_id is set; author_display_name + author_link_url
--     are NULL/empty. The display name and links come from the user's profile.
--   * Anonymous poems → author_user_id is NULL; author_display_name holds the name
--     the submitter typed; author_link_url holds at most one URL they chose to
--     attribute themselves with (any URL — Tumblr, personal site, etc.).
--   * Legacy import → anonymous, with author_link_url set to
--     "https://www.tumblr.com/<handle>" derived from the old submitter_tumblr field.
CREATE TABLE IF NOT EXISTS poems (
    id                  INTEGER PRIMARY KEY,
    short_code          TEXT    NOT NULL UNIQUE,
    title               TEXT    NOT NULL DEFAULT '',
    lines_json          TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'submitted',
    author_user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    author_display_name TEXT    NOT NULL DEFAULT '',
    author_link_url     TEXT    NOT NULL DEFAULT '',
    -- Optional citation of an existing work the poem translates / riffs on.
    -- These are NOT tags — they're a one-off relationship with a specific
    -- external work. Surfaced on the permalink as an "After ___" caption
    -- and indexed for search (1.5+, 2.11). Phase 4.5 ToS / lawyer review
    -- covers the IP wrinkle (fair-use horse-translations of copyrighted work).
    inspired_by_text    TEXT    NOT NULL DEFAULT '',
    inspired_by_url     TEXT    NOT NULL DEFAULT '',
    created_at          REAL    NOT NULL,
    published_at        REAL,
    edited_at           REAL,
    -- Counters denormalized for cheap feeds; recomputed on save.
    horse_count         INTEGER NOT NULL DEFAULT 0,
    word_count          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_poems_status_published_at ON poems(status, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_poems_author_user_id     ON poems(author_user_id);
CREATE INDEX IF NOT EXISTS idx_poems_created_at         ON poems(created_at DESC);

-- ── Tag categories ───────────────────────────────────────────────────────────
-- behavior:
--   'single_select'    — at most one tag from this category per poem (e.g. Poem Type)
--   'multi_select'     — any number of tags from this category (e.g. Theme)
--   'content_warning'  — like multi_select, but display layer treats them as warnings
-- admin_only: 1 = hidden from public; used for curation signals (Featured, Staff Pick, etc.)
CREATE TABLE IF NOT EXISTS tag_categories (
    id          INTEGER PRIMARY KEY,
    slug        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    label       TEXT    NOT NULL,
    behavior    TEXT    NOT NULL DEFAULT 'multi_select',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    admin_only  INTEGER NOT NULL DEFAULT 0,
    created_at  REAL    NOT NULL
);

-- ── Tags ─────────────────────────────────────────────────────────────────────
-- status: 'active' | 'pending' | 'rejected'
-- pending tags are user-suggested and need admin approval before they show up
-- in the editor's picker for other users.
CREATE TABLE IF NOT EXISTS tags (
    id              INTEGER PRIMARY KEY,
    slug            TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    label           TEXT    NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES tag_categories(id) ON DELETE CASCADE,
    status          TEXT    NOT NULL DEFAULT 'active',
    suggested_by    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tags_category_status ON tags(category_id, status);

-- ── Poem ↔ Tag junction ──────────────────────────────────────────────────────
-- status here is for the (poem, tag) application — admins can approve/reject
-- per-poem assignments separately from the tag's own existence.
CREATE TABLE IF NOT EXISTS poem_tags (
    poem_id     INTEGER NOT NULL REFERENCES poems(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tags(id)  ON DELETE CASCADE,
    applied_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status      TEXT    NOT NULL DEFAULT 'approved',  -- 'pending' | 'approved' | 'rejected'
    created_at  REAL    NOT NULL,
    PRIMARY KEY (poem_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_poem_tags_tag_id ON poem_tags(tag_id);

-- ── Submissions queue ────────────────────────────────────────────────────────
-- One row per poem submitted for review. Poem itself lives in poems with
-- status='submitted' until an admin moves it to 'published'.
CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY,
    poem_id         INTEGER NOT NULL UNIQUE REFERENCES poems(id) ON DELETE CASCADE,
    status          TEXT    NOT NULL DEFAULT 'pending',  -- 'pending' | 'approved' | 'rejected'
    reviewed_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at     REAL,
    review_notes    TEXT    NOT NULL DEFAULT '',
    submitted_at    REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status, submitted_at DESC);

-- ── Reports ──────────────────────────────────────────────────────────────────
-- target_type: 'poem' | 'display_name' | 'slug' | 'tag'
-- target_id holds the integer PK of the appropriate table.
-- For 'display_name' on anonymous poems, target_id is the poem id (the
-- display_name string lives on the poem row).
CREATE TABLE IF NOT EXISTS reports (
    id                  INTEGER PRIMARY KEY,
    target_type         TEXT    NOT NULL,
    target_id           INTEGER NOT NULL,
    reporter_user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reporter_ip         TEXT    NOT NULL DEFAULT '',  -- for anon rate limiting
    reason              TEXT    NOT NULL DEFAULT '',
    status              TEXT    NOT NULL DEFAULT 'pending',  -- 'pending' | 'actioned' | 'dismissed'
    created_at          REAL    NOT NULL,
    resolved_at         REAL,
    resolved_by         INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_status_created ON reports(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_target         ON reports(target_type, target_id);

-- ── Drafts ───────────────────────────────────────────────────────────────────
-- Per-user (logged-in) work-in-progress poems. Anonymous drafts live in
-- the browser's localStorage and never touch this table.
CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL DEFAULT '',
    lines_json  TEXT    NOT NULL,
    updated_at  REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drafts_user_updated ON drafts(user_id, updated_at DESC);

-- ── Stable horses (per-user, server-side) ────────────────────────────────────
-- The composition working area. One row per (user, horse name).
-- Anonymous users keep their stable in localStorage; nothing here for them.
CREATE TABLE IF NOT EXISTS stable_horses (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,    -- normalized horse name (matches dictionary key)
    display     TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    remaining   INTEGER NOT NULL DEFAULT 1,
    added_at    REAL    NOT NULL,
    PRIMARY KEY (user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_stable_user_added ON stable_horses(user_id, added_at DESC);

-- ── Pasture horses (per-user, server-side) ───────────────────────────────────
-- Long-term per-user collection of horses the user wants to keep around. Distinct
-- from `stable_horses` (the current composition's working pool) and from
-- `saved_horses` (sentiment / blue-ribbon). Anonymous users do not have a pasture;
-- the editor's "Send to My Pasture" action prompts them to sign in.
CREATE TABLE IF NOT EXISTS pasture_horses (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,    -- normalized horse name (matches dictionary key)
    display     TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    added_at    REAL    NOT NULL,
    PRIMARY KEY (user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_pasture_user_added ON pasture_horses(user_id, added_at DESC);

-- ── Horse occurrences (per-poem horse index) ──────────────────────────────────
-- Populated at poem-save time. Used for fast "poems featuring this horse" lookups.
-- One row per (poem, horse name); duplicates within a poem are counted as one.
CREATE TABLE IF NOT EXISTS horse_occurrences (
    poem_id     INTEGER NOT NULL REFERENCES poems(id) ON DELETE CASCADE,
    horse_name  TEXT    NOT NULL,    -- normalized name (matches dictionary key)
    PRIMARY KEY (poem_id, horse_name)
);

CREATE INDEX IF NOT EXISTS idx_horse_occ_name ON horse_occurrences(horse_name);

-- ── Featured sections ────────────────────────────────────────────────────────
-- Each row pins a tag to a slot on the /featured page with a custom header.
-- Any tag (public or admin-only) can be featured. sort_order controls the
-- display sequence. active=0 hides the section without deleting it.
CREATE TABLE IF NOT EXISTS featured_sections (
    id          INTEGER PRIMARY KEY,
    tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    label       TEXT    NOT NULL DEFAULT '',  -- custom header; falls back to tag label
    sort_order  INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_featured_sections_active_order ON featured_sections(active, sort_order);

-- ── Saved horses (blue-ribbon sentiment collection) ───────────────────────────
-- Private per-user collection. Feeds admin popularity stats but never surfaced
-- publicly as a count. Distinct from Pasture.
CREATE TABLE IF NOT EXISTS saved_horses (
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,    -- normalized horse name
    display     TEXT    NOT NULL,
    url         TEXT    NOT NULL DEFAULT '',
    saved_at    REAL    NOT NULL,
    PRIMARY KEY (user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_saved_horses_user_saved ON saved_horses(user_id, saved_at DESC);

-- ── Saved poems (blue-ribbon per-poem collection) ─────────────────────────────
-- Phase 1.19. Private per-user. Feeds admin stats; never surfaced as a public count.
CREATE TABLE IF NOT EXISTS saved_poems (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    poem_id   INTEGER NOT NULL REFERENCES poems(id) ON DELETE CASCADE,
    saved_at  REAL    NOT NULL,
    PRIMARY KEY (user_id, poem_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_poems_user ON saved_poems(user_id, saved_at DESC);
