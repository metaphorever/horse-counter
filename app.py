"""
app.py - Flask routes for poet.horse / Horse Counter

Public routes (no login required):
  GET  /               main input page (URL + text tabs)
  POST /               process URL or text, show count + submit option
  POST /submit         save a counted post submission (public or admin)
  POST /submit/poem    save a poem submission (public or admin)
  GET  /poetry         poetry editor
  POST /poetry/search  horse name search
  GET  /p/<short_code> poem permalink (stub)
  GET  /sign-in        Clerk sign-in page
  GET  /sign-out       clear session
  POST /auth/clerk/verify  exchange Clerk JWT for Flask session
  GET  /setup-account  pick a slug after first Clerk login
  POST /setup-account  submit slug choice
  GET  /u/<slug>       public poet profile (stub)

Admin routes (login required — Clerk role='admin' OR PIN fallback):
  POST /queue          post/queue/draft a reviewed post
  GET  /auth           start Tumblr OAuth
  GET  /callback       OAuth callback
  GET  /submissions    review pending submissions
  POST /submissions/*  submission actions
  POST /poetry/stable/*  server-persisted stable
  GET  /admin/*        admin management pages
  GET  /login          PIN fallback (admin only)
"""

import os
import re
from datetime import datetime
from flask import (
    Flask, g, request, redirect, session, url_for,
    render_template, flash, jsonify,
)
from functools import wraps

from config import (
    SECRET_KEY, SESSION_LIFETIME_SECONDS,
    TUMBLR_BLOG_NAME, HORSES_RICH_FILE, HORSES_LEGACY_FILE, HORSE_OVERRIDES_FILE,
    FAMOUS_HORSES_FILE,
    check_pin, get_horse_emoji, build_default_tags,
    OPTIONAL_TAGS, POST_SUFFIX, SEO_TAGS, format_prefix,
)
from clerk_auth import verify_clerk_token, CLERK_PUBLISHABLE_KEY
from db.users import (
    get_user_by_id, get_user_by_clerk_id, get_user_by_slug,
    create_user, validate_slug, slug_available,
    get_preferences, update_preferences,
)
from db.stable import list_stable_horses, bulk_add_stable_horses
from db.pasture import add_to_pasture
from auth import TumblrManager
from matcher import (
    HorseDictionary, ChainCounter,
    find_horses_in_text, render_chain_item, compute_stats,
    horse_appearance,
)
from post_builder import extract_post
from famous import FamousHorses
from db.conn import init_db
from poem_db import (
    save_poem as save_poem_db,
    get_poem_by_short_code,
    list_published as list_published_poems,
    get_poems_featuring_horse,
    browse_poems,
    count_browse_poems,
    get_random_published,
    get_poems_for_tag_slug,
)
from db.tags import (
    list_categories_with_tags,
    list_all_categories_with_tags,
    list_admin_only_categories_with_tags,
    apply_tags_to_poem,
    update_poem_tags,
    suggest_tag,
    tags_for_poem,
    create_tag_category,
    create_tag,
    list_featured_sections,
    list_all_featured_sections,
    add_featured_section,
    update_featured_section,
    remove_featured_section,
)
from horse_collections import (
    get_horse_states,
    toggle_pasture,
    toggle_saved_horse,
)
from poem_submissions import (
    create_for_poem      as create_poem_submission,
    load_pending         as load_pending_poem_submissions,
    load_submission      as load_poem_submission,
    approve              as approve_poem_submission,
    reject               as reject_poem_submission,
)
from poetry import (
    search_dictionary, random_horses, short_horses, load_stable, add_to_stable,
    remove_from_stable, clear_stable,
    build_poem_html, compute_poem_stats, format_poem_prefix,
    POEM_SUFFIX, build_poem_tags, order_tags,
    get_rhymes, search_by_rhyme_terms, RHYME_DEFAULT_ON,
    get_synonyms, search_by_synonym_terms, THESAURUS_DEFAULT_ON,
)
from queue_handler import (
    save_draft, load_draft, delete_draft,
    assemble_tags, build_post_body, submit_post,
)
from submissions import (
    save_submission, load_pending, load_submission, update_status,
)

# ── Horse tile appearance (mirrors JS in poetry.html / poem_permalink.html) ───

_COATS = [
    {'bg': '#7a3520', 'fg': '#f5ecd7'},
    {'bg': '#1c1c1c', 'fg': '#e8d5b0'},
    {'bg': '#7a7a7a', 'fg': '#f0ead6'},
    {'bg': '#8b3a1f', 'fg': '#fae8c8'},
    {'bg': '#c8961a', 'fg': '#2a1800'},
    {'bg': '#c8bfaa', 'fg': '#1c1008'},
    {'bg': '#4a2812', 'fg': '#ead8b8'},
    {'bg': '#8a6a5a', 'fg': '#f0e4d0'},
]

def _tile_style(name: str) -> dict:
    h = sum(ord(c) for c in name)
    coat = _COATS[h % len(_COATS)]
    return {
        'style': f"--bg:{coat['bg']};--fg:{coat['fg']}",
        'cls':   ' rev' if h % 2 == 0 else '',
    }


# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.jinja_env.globals['tile_style'] = _tile_style
app.permanent_session_lifetime = SESSION_LIFETIME_SECONDS

# ── Initialise singletons ─────────────────────────────────────────────────────

print("Initialising Horse Counter...")
init_db()
dictionary     = HorseDictionary(HORSES_RICH_FILE, HORSES_LEGACY_FILE, HORSE_OVERRIDES_FILE)
famous_horses  = FamousHorses(FAMOUS_HORSES_FILE)
tumblr         = TumblrManager()
print(f"Ready. Dictionary: {dictionary.source}, "
      f"Tumblr: {'connected' if tumblr.authenticated else 'not connected'}")


# ── Request lifecycle ─────────────────────────────────────────────────────────

@app.before_request
def load_current_user():
    """Populate g.current_user from Flask session on every request."""
    g.current_user = None
    user_id = session.get('user_id')
    if user_id:
        g.current_user = get_user_by_id(user_id)
        if g.current_user is None:
            # Row was deleted — clear stale session
            session.pop('user_id', None)


def _is_admin() -> bool:
    """True if the current request has admin privileges (Clerk role or PIN)."""
    if session.get('logged_in'):
        return True
    user = g.get('current_user')
    return user is not None and user.get('role') == 'admin'


# ── Template globals ──────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    """Make is_admin, current_user, and Clerk key available in every template."""
    return {
        'is_admin':              _is_admin(),
        'current_user':          g.get('current_user'),
        'clerk_publishable_key': CLERK_PUBLISHABLE_KEY,
        'tumblr_auth':           tumblr.authenticated,
        'blog_name':             TUMBLR_BLOG_NAME,
    }


def _sanitize_name(raw: str) -> str:
    """Strip HTML-dangerous chars, limit length."""
    return re.sub(r'[<>&"\'\\]', '', raw or '').strip()[:60]

def _sanitize_tumblr(raw: str) -> str:
    """Strip leading @, restrict to valid Tumblr username characters."""
    handle = (raw or '').lstrip('@').strip().lower()
    return re.sub(r'[^a-z0-9-]', '', handle)[:32]

def _attribution_html(name: str, tumblr: str, prefix: str = 'Submitted by', title: str = '') -> str:
    """
    Build an attribution line for the post body, or empty string if nothing to show.

    With title: produces '<em>title</em> by Author' (poem header format; prefix ignored).
    Without title: produces 'prefix Author' (standard submission format).
    """
    if title:
        title_html = f'<em>{title}</em>'
        if name or tumblr:
            display = name or f'@{tumblr}'
            author = f'<a href="https://www.tumblr.com/{tumblr}">{display}</a>' if tumblr else display
            return f'<p>{title_html} by {author}</p>'
        return f'<p>{title_html}</p>'
    if not name and not tumblr:
        return ''
    display = name or f'@{tumblr}'
    if tumblr:
        return f'<p>{prefix} <a href="https://www.tumblr.com/{tumblr}">{display}</a></p>'
    return f'<p>{prefix} {name}</p>'


@app.template_filter('datefmt')
def datefmt(ts):
    return datetime.fromtimestamp(ts).strftime('%b %d %H:%M')


def _auto_check_tags(post_data: dict) -> set:
    """Tags to pre-check on the review page based on post content."""
    auto = set()
    all_text = ' '.join(
        item.get('text', '') for item in post_data.get('chain', [])
    )
    has_media = bool(re.search(r'\[{3}(?:IMAGE|GIF|VIDEO)', all_text))
    if re.search(r'\[{3}(?:IMAGE|GIF)', all_text):
        auto.add('horse image')
        auto.add('image')
    if re.search(r'\[{3}GIF', all_text):
        auto.add('animated gif')
    if '[[[VIDEO]]]' in all_text:
        auto.add('video')
    if not has_media:
        auto.add('text post')
    if re.search(r'\bhorse\b', all_text, re.IGNORECASE):
        auto.add('horse mention')
    if post_data.get('is_reply'):
        auto.add('reply')
    return auto


# ── Auth guard ────────────────────────────────────────────────────────────────

def login_required(f):
    """Require Clerk auth (role=admin) OR PIN fallback session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _is_admin():
            if (request.content_type or '').startswith('application/json') or \
               request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Session expired — please reload the page'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def user_required(f):
    """Require any signed-in user (regular Clerk user or admin)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.get('current_user') is None and not session.get('logged_in'):
            return redirect(url_for('sign_in'))
        return f(*args, **kwargs)
    return decorated


# ── Login / logout ────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        pin = request.form.get('pin', '')
        if check_pin(pin):
            session.permanent = True
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='Incorrect PIN')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Clerk sign-in / sign-out ──────────────────────────────────────────────────

@app.route('/sign-in')
def sign_in():
    """Render the Clerk-powered sign-in page."""
    if g.get('current_user') or session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('sign_in.html')


@app.route('/sign-out')
def sign_out():
    """Clear the Flask session; page JS will also call Clerk.signOut()."""
    session.clear()
    return render_template('sign_out.html')


@app.route('/auth/clerk/verify', methods=['POST'])
def clerk_verify():
    """
    Exchange a Clerk session JWT for a Flask session.

    Called by the Clerk JS on the sign-in page after the user authenticates.
    Expects: Authorization: Bearer <token>
    Returns JSON: { redirect: <url> } or { error: <msg> }
    """
    token = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if not token:
        return jsonify({'error': 'No token provided'}), 400

    clerk_user_id = verify_clerk_token(token)
    if not clerk_user_id:
        return jsonify({'error': 'Invalid or expired token'}), 401

    user = get_user_by_clerk_id(clerk_user_id)
    if user:
        session.permanent = True
        session['user_id'] = user['id']
        return jsonify({'redirect': url_for('index')})

    # First login — stash the Clerk ID and send to slug picker
    session['pending_clerk_id'] = clerk_user_id
    # Also carry the display name Clerk gave us if provided in the request body
    body = request.get_json(silent=True) or {}
    if body.get('display_name'):
        session['pending_display_name'] = str(body['display_name'])[:80]
    return jsonify({'redirect': url_for('setup_account')})


@app.route('/setup-account', methods=['GET', 'POST'])
def setup_account():
    """
    Slug-picker shown on first Clerk login.
    Session must contain 'pending_clerk_id'; otherwise redirect to sign-in.
    """
    clerk_id = session.get('pending_clerk_id')
    if not clerk_id:
        # Not in the middle of a fresh sign-in — redirect appropriately
        if g.get('current_user'):
            return redirect(url_for('index'))
        return redirect(url_for('sign_in'))

    display_name = session.get('pending_display_name', '')
    error = None

    if request.method == 'POST':
        slug         = request.form.get('slug', '').strip().lower()
        display_name = request.form.get('display_name', '').strip()[:80] or display_name

        error = validate_slug(slug)
        if error is None and not slug_available(slug):
            error = f'"{slug}" is already taken — please choose another.'

        if error is None:
            user = create_user(
                clerk_id     = clerk_id,
                slug         = slug,
                display_name = display_name or slug,
            )
            session.pop('pending_clerk_id',    None)
            session.pop('pending_display_name', None)
            session.permanent = True
            session['user_id'] = user['id']
            flash('Welcome to poet.horse!', 'ok')
            return redirect(url_for('index'))

    return render_template('setup_account.html',
        display_name=display_name,
        error=error,
    )


# ── Account sync (Phase 0.5) ──────────────────────────────────────────────────

# Preference keys synced from localStorage. Keep stable names — clients clear
# the matching local keys after a successful sync.
_SYNCABLE_PREF_KEYS = ('poem_name', 'poem_tumblr', 'page_size')


@app.route('/me/sync', methods=['POST'])
def me_sync():
    """
    Merge anonymous localStorage state into the logged-in user's account.

    Body (all fields optional):
        {
          "stable":     [{name, display, url, remaining}, ...],
          "poem_name":  "...",
          "poem_tumblr": "...",
          "page_size":  "25"
        }

    Returns the merged server-side state so the client can replace its in-memory
    copy and clear local storage:
        { ok: true, stable: [...], preferences: {...}, added: <int> }
    """
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Not signed in'}), 401

    body = request.get_json(silent=True) or {}

    # ── stable horses ─────────────────────────────────────────────────────────
    raw_stable = body.get('stable') or []
    cleaned = []
    if isinstance(raw_stable, list):
        for h in raw_stable[:200]:  # hard cap, defensive
            if not isinstance(h, dict):
                continue
            name = (h.get('name') or '').strip()
            if not name:
                continue
            cleaned.append({
                'name':      name[:200],
                'display':   (h.get('display') or name)[:200],
                'url':       (h.get('url') or '')[:500],
                'remaining': max(1, min(99, int(h.get('remaining') or 1))),
            })
    added = bulk_add_stable_horses(user['id'], cleaned) if cleaned else 0

    # ── preferences ───────────────────────────────────────────────────────────
    pref_updates = {}
    for key in _SYNCABLE_PREF_KEYS:
        if key in body and body[key] not in (None, ''):
            pref_updates[key] = str(body[key])[:80]
    prefs = update_preferences(user['id'], pref_updates) if pref_updates else get_preferences(user['id'])

    return jsonify({
        'ok':          True,
        'added':       added,
        'stable':      list_stable_horses(user['id']),
        'preferences': prefs,
    })


# Preference keys clients can write through /me/preferences. Allow-listed and
# value-validated below so the endpoint never becomes a free-form key/value
# store on the user row.
_USER_PREF_WRITES = {
    'poem_view_mode': lambda v: v if v in ('plain', 'pasture') else None,
}


@app.route('/me/preferences', methods=['POST'])
def me_preferences():
    """
    Persist a small set of UI preferences for the signed-in user.

    Body: {<pref_key>: <value>, ...} — keys must be in _USER_PREF_WRITES
    and values are validated by the matching validator. Unknown keys and
    values that fail validation are silently dropped.

    Returns: { ok: true, preferences: {<merged dict>} }
    """
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Not signed in'}), 401

    body = request.get_json(silent=True) or {}
    updates = {}
    for key, validator in _USER_PREF_WRITES.items():
        if key in body:
            cleaned = validator(body[key])
            if cleaned is not None:
                updates[key] = cleaned

    prefs = update_preferences(user['id'], updates) if updates else get_preferences(user['id'])
    return jsonify({'ok': True, 'preferences': prefs})


# ── Legal pages (Phase 0.6) ──────────────────────────────────────────────────

@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/data-deletion')
def data_deletion():
    return render_template('data_deletion.html')


# ── Poet profile ──────────────────────────────────────────────────────────────

@app.route('/u/<slug>')
def user_profile(slug):
    """Public poet profile. Phase 0.4 stub — full version in Phase 1.13."""
    user = get_user_by_slug(slug)
    if not user:
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error=f'No poet found with the slug "{slug}"',
        ), 404
    return render_template('user_profile.html', poet=user)


# ── Public browse / discover stubs (Phase 1.1) ───────────────────────────────

@app.route('/count')
def count():
    return redirect(url_for('index'))


@app.route('/featured')
def featured():
    sections = list_featured_sections()
    for sec in sections:
        sec['display_label'] = sec['section_label'] or sec['tag_label']
        sec['poems'] = get_poems_for_tag_slug(sec['tag_slug'], limit=20)
    return render_template('featured.html', sections=sections)


_BROWSE_PER_PAGE = 20

@app.route('/browse')
def browse():
    sort       = request.args.get('sort', 'newest')
    tag_slug   = request.args.get('tag') or None
    attributed = request.args.get('attributed') == '1'
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1

    poems      = browse_poems(sort=sort, tag_slug=tag_slug, page=page,
                               per_page=_BROWSE_PER_PAGE, attributed=attributed)
    total      = count_browse_poems(tag_slug=tag_slug, attributed=attributed)
    total_pages = max(1, -(-total // _BROWSE_PER_PAGE))  # ceiling div

    all_tags   = list_categories_with_tags()  # public tags only for the filter UI
    return render_template(
        'poem_index.html',
        poems       = poems,
        sort        = sort,
        tag_slug    = tag_slug,
        attributed  = attributed,
        page        = page,
        total_pages = total_pages,
        total       = total,
        all_tags    = all_tags,
    )


@app.route('/random')
def random_poem():
    code = get_random_published()
    if code:
        return redirect(url_for('poem_permalink', short_code=code))
    flash('No published poems yet — be the first!', 'info')
    return redirect(url_for('browse'))


# ── Admin: featured sections + tag management (Phase 1.8) ─────────────────────

@app.route('/admin/featured')
@login_required
def admin_featured():
    sections   = list_all_featured_sections()
    admin_cats = list_admin_only_categories_with_tags()
    all_cats   = list_all_categories_with_tags()
    return render_template(
        'admin_featured.html',
        sections   = sections,
        admin_cats = admin_cats,
        all_cats   = all_cats,
    )


@app.route('/admin/featured/section/add', methods=['POST'])
@login_required
def admin_featured_section_add():
    try:
        tag_id     = int(request.form.get('tag_id', 0))
        label      = (request.form.get('label') or '').strip()
        sort_order = int(request.form.get('sort_order') or 0)
    except (ValueError, TypeError):
        flash('Invalid input.', 'error')
        return redirect(url_for('admin_featured'))
    result = add_featured_section(tag_id, label=label, sort_order=sort_order)
    if result is None:
        flash('That tag is already a featured section.', 'error')
    else:
        flash('Featured section added.', 'success')
    return redirect(url_for('admin_featured'))


@app.route('/admin/featured/section/<int:section_id>/update', methods=['POST'])
@login_required
def admin_featured_section_update(section_id):
    label      = request.form.get('label')
    active_raw = request.form.get('active')
    try:
        sort_order = int(request.form['sort_order']) if 'sort_order' in request.form else None
    except (ValueError, TypeError):
        sort_order = None
    active = (active_raw == '1') if active_raw is not None else None
    update_featured_section(section_id, label=label, sort_order=sort_order, active=active)
    flash('Section updated.', 'success')
    return redirect(url_for('admin_featured'))


@app.route('/admin/featured/section/<int:section_id>/remove', methods=['POST'])
@login_required
def admin_featured_section_remove(section_id):
    remove_featured_section(section_id)
    flash('Featured section removed.', 'success')
    return redirect(url_for('admin_featured'))


@app.route('/admin/tag-category/add', methods=['POST'])
@login_required
def admin_tag_category_add():
    label      = (request.form.get('label') or '').strip()
    behavior   = request.form.get('behavior', 'multi_select')
    admin_only = request.form.get('admin_only') == '1'
    try:
        sort_order = int(request.form.get('sort_order') or 0)
    except (ValueError, TypeError):
        sort_order = 0
    result = create_tag_category(label, behavior=behavior, admin_only=admin_only, sort_order=sort_order)
    if result is None:
        flash(f'Category "{label}" already exists or label is invalid.', 'error')
    else:
        flash(f'Category "{label}" created.', 'success')
    return redirect(url_for('admin_featured'))


@app.route('/admin/tag/add', methods=['POST'])
@login_required
def admin_tag_add():
    try:
        category_id = int(request.form.get('category_id', 0))
    except (ValueError, TypeError):
        flash('Invalid category.', 'error')
        return redirect(url_for('admin_featured'))
    label  = (request.form.get('label') or '').strip()
    result = create_tag(category_id, label)
    if result is None:
        flash(f'Tag "{label}" already exists in that category or label is invalid.', 'error')
    else:
        flash(f'Tag "{label}" created.', 'success')
    return redirect(url_for('admin_featured'))


@app.route('/poem/<short_code>/tags', methods=['POST'])
@login_required
def poem_tags_update(short_code):
    poem = get_poem_by_short_code(short_code)
    if not poem:
        flash('Poem not found.', 'error')
        return redirect(url_for('browse'))

    tier = request.form.get('tier', 'public')  # 'public' | 'admin'
    try:
        new_ids = [int(t) for t in request.form.getlist('tag_ids') if t]
    except (ValueError, TypeError):
        flash('Invalid tag data.', 'error')
        return redirect(url_for('poem_permalink', short_code=short_code))

    # Keep tags from the tier we're not editing so they survive the replace.
    current = tags_for_poem(poem['id'])
    if tier == 'public':
        keep_ids = [r['id'] for r in current if r['admin_only']]
    else:
        keep_ids = [r['id'] for r in current if not r['admin_only']]

    user = g.get('current_user')
    applied_by = user['id'] if user else None
    update_poem_tags(poem['id'], keep_ids + new_ids, applied_by=applied_by)
    flash('Tags updated.', 'success')
    return redirect(url_for('poem_permalink', short_code=short_code))


@app.route('/pasture')
def pasture():
    return render_template('coming_soon.html',
        title='Pasture',
        description='A field of horses. Public by default — your personal collection when signed in. Coming in Phase 1.19.',
        roadmap_task='1.19',
    )


# ── User account pages (/me/*) stubs (Phase 1.1) ─────────────────────────────

@app.route('/me/published')
@user_required
def me_published():
    return render_template('coming_soon.html',
        title='Published Poems',
        description='Your published poems, newest first. Coming in Phase 1.15.',
        roadmap_task='1.15',
    )


@app.route('/me/drafts')
@user_required
def me_drafts():
    return render_template('coming_soon.html',
        title='Unpublished / WIP',
        description='Drafts and poems awaiting review. Coming in Phase 1.13.',
        roadmap_task='1.13',
    )


@app.route('/me/pasture')
@user_required
def me_pasture():
    return render_template('coming_soon.html',
        title='My Pasture',
        description='Your personal working collection of horses. Coming in Phase 1.19.',
        roadmap_task='1.19',
    )


@app.route('/me/pasture/add', methods=['POST'])
def me_pasture_add():
    """Add one horse to the signed-in user's pasture.

    Body: { "name": "...", "display": "...", "url": "..." }
    Returns: { "ok": true, "added": <bool> }  (added=false if already present)
    """
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Sign in to save horses to your pasture'}), 401
    body = request.get_json(silent=True) or {}
    name    = (body.get('name')    or '').strip()[:200]
    display = (body.get('display') or name).strip()[:200]
    url     = (body.get('url')     or '').strip()[:500]
    if not name:
        return jsonify({'error': 'Missing horse name'}), 400
    added = add_to_pasture(user['id'], name, display, url)
    return jsonify({'ok': True, 'added': added})


@app.route('/me/saved-poems')
@user_required
def me_saved_poems():
    return render_template('coming_soon.html',
        title='Saved Poems',
        description='Poems you have saved with the blue-ribbon. Coming in Phase 1.19.',
        roadmap_task='1.19',
    )


@app.route('/me/saved-horses')
@user_required
def me_saved_horses():
    return render_template('coming_soon.html',
        title='Saved Horses',
        description='Horses you have saved with the blue-ribbon. Coming in Phase 1.19.',
        roadmap_task='1.19',
    )


@app.route('/me/profile')
@user_required
def me_profile():
    return render_template('coming_soon.html',
        title='Edit Profile',
        description='Edit your display name and profile links. Coming in Phase 1.15.',
        roadmap_task='1.15',
    )


# ── Main page ─────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def index():
    is_admin = bool(session.get('logged_in'))

    if request.method == 'GET':
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
        )

    form_type = request.form.get('type', 'url')
    form_data = {
        'url':        request.form.get('url', ''),
        'text':       request.form.get('text', ''),
        'reply_url':  request.form.get('reply_url', ''),
        'reply_text': request.form.get('reply_text', ''),
    }
    active_tab = {'url': 'url', 'text': 'text', 'reply': 'reply'}.get(form_type, 'url')

    def error(msg):
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab=active_tab,
            form=form_data,
            error=msg,
        )

    try:
        if form_type == 'url':
            url = form_data['url'].strip()
            if not url:
                return error("Enter a URL")

            post_data = extract_post(
                url,
                # Authenticated API (OAuth, has posting rights) for admins only.
                # Public users use the consumer-key-only public API path so the
                # OAuth token is never exercised on their behalf.
                make_api_request=tumblr.make_request if (tumblr.authenticated and is_admin) else None,
            )
            if not post_data:
                return error("Could not fetch post — check the URL or try again")

            return _process_chain(post_data, active_tab='url', form=form_data, is_admin=is_admin)

        elif form_type == 'text':
            text = form_data['text'].strip()
            if not text:
                return error("Enter some text")

            pseudo_post = {
                'blog_name':    '',
                'post_id':      '',
                'post_url':     '',
                'reblog_key':   '',
                'chain':        [{'username': '', 'text': text}],
                'is_multi':     False,
                'is_fallback':  False,
                'is_text_post': True,
            }
            return _process_chain(pseudo_post, active_tab='text', form=form_data, is_admin=is_admin)

        elif form_type == 'reply':
            if not is_admin:
                return error("Reply mode is admin only")

            reply_url  = form_data['reply_url'].strip()
            reply_text = form_data['reply_text'].strip()
            if not reply_url:
                return error("Enter the post URL to reply to")
            if not reply_text:
                return error("Enter your reply text")

            post_data = extract_post(
                reply_url,
                make_api_request=tumblr.make_request if tumblr.authenticated else None,
            )
            if not post_data:
                return error("Could not fetch post — check the URL or try again")

            post_data = dict(post_data)
            post_data['reply_text']  = reply_text
            post_data['is_reply']    = True
            post_data['reply_chain'] = post_data['chain']
            post_data['chain']       = [{'username': 'reply', 'text': reply_text}]

            return _process_chain(post_data, active_tab='reply', form=form_data, is_admin=is_admin)

    except Exception as e:
        import traceback; traceback.print_exc()
        return error(f"Unexpected error: {e}")


def _process_chain(post_data: dict, active_tab: str, form: dict, is_admin: bool = False):
    """
    Run matching on all chain items with a shared ChainCounter.

    Admin + Tumblr connected + horses found → review page (direct post flow).
    Everyone else → count result page.
    Public + horses found → also saves a draft so the user can submit it.
    """
    chain   = post_data['chain']
    counter = ChainCounter(dictionary)

    chain_matches = []
    for item in chain:
        matches = find_horses_in_text(item['text'], dictionary)
        chain_matches.append(matches)

    rendered_parts     = []
    total_linked_words = 0

    # Collect famous horses found across all chain items (deduplicated, ordered)
    famous_found = []
    famous_seen_keys: set = set()
    famous_tags: list = []
    famous_tags_seen: set = set()
    for matches in chain_matches:
        for m in matches:
            info = famous_horses.lookup(m['name'])
            if info:
                if m['name'] not in famous_seen_keys:
                    famous_seen_keys.add(m['name'])
                    famous_found.append(info)
                for tag in info['tags']:
                    if tag not in famous_tags_seen:
                        famous_tags_seen.add(tag)
                        famous_tags.append(tag)

    for item, matches in zip(chain, chain_matches):
        html, linked_words = render_chain_item(item['text'], matches, counter, famous=famous_horses)
        total_linked_words += linked_words
        rendered_parts.append({'username': item['username'], 'html': html})

    raw_texts = [item['text'] for item in chain]
    stats     = compute_stats(raw_texts, counter)
    stats['linked_words'] = total_linked_words
    total_words = stats['total_words']
    stats['horse_density'] = (
        round(total_linked_words / total_words * 100, 1)
        if total_words > 0 else 0.0
    )

    horse_count = counter.total_linked()

    # ── Build combined HTML ──
    if post_data.get('is_multi') or len(rendered_parts) > 1:
        parts = []
        for i, part in enumerate(rendered_parts):
            if part['username']:
                emoji = get_horse_emoji(part['username'])
                parts.append(f'<p class="chain-username">{emoji} @{part["username"]}</p>')
            parts.append(part['html'])
            if i < len(rendered_parts) - 1:
                parts.append('<hr class="chain-sep">')
        linked_html = ''.join(parts)
    else:
        part = rendered_parts[0]
        if part['username']:
            emoji = get_horse_emoji(part['username'])
            linked_html = f'<p class="chain-username">{emoji} @{part["username"]}</p>{part["html"]}'
        else:
            linked_html = part['html']

    # ── All users with horses → save draft and route to queue ──
    draft_id = None
    if horse_count > 0:
        draft_id = save_draft({
            'post_data':    post_data,
            'horse_count':  horse_count,
            'linked_html':  linked_html,
            'stats':        stats,
            'famous_tags':  famous_tags,
            'is_text_post': post_data.get('is_text_post', False),
            'is_reply':     post_data.get('is_reply', False),
            'is_fallback':  post_data.get('is_fallback', False),
            'is_admin':     is_admin,
        })

    return render_template('index.html',
        horses_loaded=dictionary.loaded,
        active_tab=active_tab,
        form=form,
        result={
            'count':       horse_count,
            'stats':       stats,
            'linked_html': linked_html if horse_count > 0 else None,
            'draft_id':    draft_id,
        },
    )


# ── Queue / post / draft ──────────────────────────────────────────────────────

@app.route('/queue', methods=['POST'])
@login_required
def queue_post():
    if not tumblr.authenticated:
        return redirect(url_for('index'))

    draft_id = request.form.get('id', '')
    draft    = load_draft(draft_id)

    if not draft:
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error='Draft expired — please re-process the post',
        )

    action = request.form.get('action', 'queue')
    prefix = request.form.get('pre', '')
    middle = request.form.get('mid', '')
    suffix = request.form.get('suf', POST_SUFFIX)

    prefix_tags = [t.strip() for t in request.form.get('prefix_tags', '').split(',') if t.strip()]
    tags = assemble_tags(
        default_tags=prefix_tags + request.form.getlist('tag_default'),
        optional_tags=request.form.getlist('tag_optional'),
        custom_tags=request.form.get('tags_custom', ''),
        seo_tags=SEO_TAGS,
    )

    body = build_post_body(prefix, draft['linked_html'], middle, suffix)

    success, err_msg = submit_post(
        draft=draft,
        action=action,
        body=body,
        tags=tags,
        make_request=tumblr.make_request,
    )

    if success:
        delete_draft(draft_id)
        action_label = {'post': 'published', 'queue': 'queued', 'draft': 'saved as draft'}.get(action, 'queued')
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            queued=action_label,
        )

    return render_template('review.html',
        draft_id=draft_id,
        horse_count=draft['horse_count'],
        stats=draft.get('stats'),
        content=draft['linked_html'],
        pre=prefix,
        mid=middle,
        suf=suffix,
        default_tags=request.form.getlist('tag_default'),
        optional_tags=OPTIONAL_TAGS,
        custom_tags=request.form.get('tags_custom', ''),
        auto_check_tags=_auto_check_tags(draft.get('post_data', {})),
        is_fallback=draft.get('is_fallback', False),
        error=err_msg,
    )


# ── Public submissions ────────────────────────────────────────────────────────

@app.route('/submit', methods=['POST'])
def public_submit():
    """Accept a counted post submission (public or admin)."""
    draft_id = request.form.get('draft_id', '')
    draft    = load_draft(draft_id)

    if not draft:
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error='Submission timed out — please count again and try again',
        )

    is_admin         = bool(session.get('logged_in'))
    sub_type         = 'text' if draft.get('is_text_post') else 'url'
    submitter_name   = _sanitize_name(request.form.get('submitter_name', ''))
    submitter_tumblr = _sanitize_tumblr(request.form.get('submitter_tumblr', ''))
    save_submission(sub_type, {
        'post_data':        draft.get('post_data', {}),
        'horse_count':      draft['horse_count'],
        'linked_html':      draft['linked_html'],
        'stats':            draft.get('stats', {}),
        'famous_tags':      draft.get('famous_tags', []),
        'is_text_post':     draft.get('is_text_post', False),
        'is_fallback':      draft.get('is_fallback', False),
        'is_admin':         is_admin,
        'submitter_name':   submitter_name,
        'submitter_tumblr': submitter_tumblr,
    })
    delete_draft(draft_id)

    return render_template('index.html',
        horses_loaded=dictionary.loaded,
        active_tab='url',
        form={},
        submitted=True,
    )


@app.route('/submit/poem', methods=['POST'])
def submit_poem_public():
    """
    Accept a poem submission. New SQLite-backed flow:
      1. Insert into poems with status='submitted'.
      2. Insert into submissions with status='pending'.
    Anonymous attribution: display_name + a single optional link URL. We
    accept either a raw URL via `submitter_link` or fall back to converting
    a Tumblr handle from `submitter_tumblr` (legacy clients).
    """
    from flask import jsonify
    data   = request.get_json()
    lines  = data.get('lines', [])

    if not any(lines):
        return jsonify({'ok': False, 'error': 'Poem is empty'})

    submitter_name   = _sanitize_name(data.get('submitter_name', ''))
    poem_title       = _sanitize_name(data.get('poem_title', ''))
    submitter_link   = (data.get('submitter_link') or '').strip()[:300]
    submitter_tumblr = _sanitize_tumblr(data.get('submitter_tumblr', ''))
    inspired_text    = (data.get('inspired_by_text') or '').strip()[:300]
    inspired_url     = (data.get('inspired_by_url')  or '').strip()[:300]
    raw_tag_ids      = data.get('tag_ids') or []

    author_link_url = submitter_link
    if not author_link_url and submitter_tumblr:
        author_link_url = f'https://www.tumblr.com/{submitter_tumblr}'

    tag_ids = []
    if isinstance(raw_tag_ids, list):
        for t in raw_tag_ids[:40]:  # generous cap; helper revalidates against DB
            try:
                tag_ids.append(int(t))
            except (TypeError, ValueError):
                continue

    poem = save_poem_db(
        lines               = lines,
        title               = poem_title,
        author_user_id      = None,           # anonymous; logged-in flow lands later
        author_display_name = submitter_name,
        author_link_url     = author_link_url,
        inspired_by_text    = inspired_text,
        inspired_by_url     = inspired_url,
        status              = 'submitted',
    )
    if tag_ids:
        # Submitter-applied tags land as 'pending' on the poem_tags row so the
        # admin queue (1.13) can approve / strip / add per-poem.
        apply_tags_to_poem(poem['id'], tag_ids, applied_by=None, status='pending')
    create_poem_submission(poem['id'])

    return jsonify({
        'ok':         True,
        'message':    'Poem submitted for review!',
        'short_code': poem['short_code'],
    })


@app.route('/tags/suggest', methods=['POST'])
def tags_suggest():
    """Create a pending tag suggestion scoped to a category. Returns the new
    tag id + slug so the editor can immediately reflect it as a chosen tag.

    Anonymous suggestions are allowed (suggested_by=NULL). Per-IP rate
    limiting comes in 1.17.
    """
    user = g.get('current_user')
    body = request.get_json(silent=True) or {}
    try:
        category_id = int(body.get('category_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'Invalid category'}), 400
    label = (body.get('label') or '').strip()[:60]
    if not label:
        return jsonify({'ok': False, 'error': 'Tag label required'}), 400

    new_id = suggest_tag(category_id, label, suggested_by=(user['id'] if user else None))
    if not new_id:
        return jsonify({'ok': False, 'error': 'That tag already exists in this category'}), 409
    return jsonify({'ok': True, 'tag': {'id': new_id, 'label': label}})


# ── Admin submission review ───────────────────────────────────────────────────

@app.route('/submissions')
@login_required
def submissions():
    pending = load_pending()
    return render_template('submissions.html', submissions=pending)


@app.route('/submissions/approve', methods=['POST'])
@login_required
def approve_submission():
    sub_id = request.form.get('id', '')
    sub    = load_submission(sub_id)
    if not sub:
        return redirect(url_for('submissions'))

    horse_count      = sub.get('horse_count', 0)
    stats            = sub.get('stats') or {}
    density          = stats.get('horse_density', 0.0)
    submitter_name   = sub.get('submitter_name', '')
    submitter_tumblr = sub.get('submitter_tumblr', '')

    draft_id = save_draft({
        'post_data':    sub.get('post_data', {}),
        'horse_count':  horse_count,
        'linked_html':  sub.get('linked_html', ''),
        'stats':        stats,
        'is_text_post': sub.get('is_text_post', False),
        'is_reply':     False,
        'is_fallback':  sub.get('is_fallback', False),
    })
    update_status(sub_id, 'approved')

    is_poem    = sub.get('type') == 'poem'
    sub_is_admin = sub.get('is_admin', False)
    is_user_sub  = not sub_is_admin or bool(submitter_name or submitter_tumblr)
    name_tag     = f'by {submitter_name}' if submitter_name else ''
    tumblr_tag   = submitter_tumblr if submitter_tumblr else ''
    prefix_tags  = ''
    extra_tags   = ''

    if is_poem:
        # Poem: new prefix format with graceful degradation; body = prefix + html + suffix
        pre  = format_poem_prefix(horse_count, sub.get('poem_title', ''), submitter_name, submitter_tumblr)
        mid  = ''
        suf  = POEM_SUFFIX
        poem_tag_list  = build_poem_tags(horse_count, submitter_name, submitter_tumblr, is_admin=sub_is_admin)
        extra_tags = ','.join(poem_tag_list)
    else:
        # URL/text: standard count prefix; "Submitted by Name" in mid
        pre  = format_prefix(horse_count, False, density)
        mid  = _attribution_html(submitter_name, submitter_tumblr, prefix='Submitted by')
        suf  = POST_SUFFIX
        famous_tags_list = sub.get('famous_tags', [])
        # Attribution as prefix (always first), famous tags in custom field
        attr_parts = [t for t in [
            'user submission' if is_user_sub else '',
            name_tag, tumblr_tag,
        ] if t]
        prefix_tags = ','.join(attr_parts)
        extra_tags  = ','.join(famous_tags_list)

    return render_template('review.html',
        draft_id=draft_id,
        horse_count=horse_count,
        stats=stats,
        content=sub.get('linked_html', ''),
        pre=pre,
        mid=mid,
        suf=suf,
        prefix_tags=prefix_tags,
        default_tags=build_default_tags(horse_count, density),
        optional_tags=OPTIONAL_TAGS,
        custom_tags=extra_tags,
        auto_check_tags=_auto_check_tags(sub.get('post_data', {})),
        is_fallback=sub.get('is_fallback', False),
        error=None,
    )


@app.route('/submissions/reject', methods=['POST'])
@login_required
def reject_submission():
    update_status(request.form.get('id', ''), 'rejected')
    return redirect(url_for('submissions'))


# ── Tumblr OAuth ──────────────────────────────────────────────────────────────

@app.route('/auth')
@login_required
def auth():
    from config import TUMBLR_CONSUMER_KEY
    if not TUMBLR_CONSUMER_KEY:
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error='TUMBLR_CONSUMER_KEY not set — add it in PythonAnywhere environment variables',
        )
    session.permanent = True
    auth_url = tumblr.get_auth_url()
    if auth_url:
        return redirect(auth_url)
    return render_template('index.html',
        horses_loaded=dictionary.loaded,
        active_tab='url',
        form={},
        error='Could not generate Tumblr auth URL',
    )


@app.route('/callback')
@login_required
def callback():
    code  = request.args.get('code')
    error = request.args.get('error')
    state = request.args.get('state')

    if error:
        return render_template('index.html',
            horses_loaded=dictionary.loaded, active_tab='url', form={},
            error=f'Tumblr auth error: {error}',
        )

    if not code:
        return render_template('index.html',
            horses_loaded=dictionary.loaded, active_tab='url', form={},
            error='Auth failed: no code received',
        )

    if state != session.get('oauth_state'):
        return render_template('index.html',
            horses_loaded=dictionary.loaded, active_tab='url', form={},
            error='Auth failed: state mismatch (try again)',
        )

    code_verifier = session.pop('code_verifier', None)
    session.pop('oauth_state', None)

    if not code_verifier:
        return render_template('index.html',
            horses_loaded=dictionary.loaded, active_tab='url', form={},
            error='Auth failed: missing code verifier (session may have expired)',
        )

    if tumblr.complete_auth(code, code_verifier):
        return redirect(url_for('index'))

    return render_template('index.html',
        horses_loaded=dictionary.loaded, active_tab='url', form={},
        error='Auth failed: could not exchange code for token',
    )


# ── Poetry editor ─────────────────────────────────────────────────────────────

@app.route('/poetry')
def poetry_editor():
    import json
    is_admin = bool(session.get('logged_in'))
    # Admin uses the shared file-based stable. Logged-in users get their
    # per-account stable from the DB. Anonymous users start from empty and
    # the client hydrates from localStorage.
    if is_admin:
        stable = load_stable()
        prefs  = {}
    elif g.get('current_user'):
        stable = list_stable_horses(g.current_user['id'])
        prefs  = get_preferences(g.current_user['id'])
    else:
        stable = []
        prefs  = {}
    tag_categories = list_categories_with_tags()
    return render_template('poetry.html',
        stable_json=json.dumps(stable),
        user_prefs_json=json.dumps(prefs),
        optional_tags_json=json.dumps(OPTIONAL_TAGS),
        tag_categories_json=json.dumps(tag_categories),
    )


@app.route('/poetry/search', methods=['POST'])
def poetry_search():
    from flask import jsonify
    data    = request.get_json(silent=True) or {}
    query   = data.get('query', '')
    results = search_dictionary(query, dictionary)
    return jsonify(results)


@app.route('/poetry/random', methods=['POST'])
def poetry_random():
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    n    = min(int(data.get('n', 5)), 20)
    return jsonify({'ok': True, 'results': random_horses(dictionary, n)})


@app.route('/poetry/short', methods=['POST'])
def poetry_short():
    from flask import jsonify
    results = short_horses(dictionary)
    return jsonify({'ok': True, 'results': results, 'total': len(results)})


@app.route('/poetry/rhyme/terms', methods=['POST'])
def poetry_rhyme_terms():
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    word = (data.get('word') or '').strip()
    if not word:
        return jsonify({'terms': [], 'error': 'No word provided'})
    terms = get_rhymes(word)
    if not terms:
        return jsonify({'terms': [], 'error': f'No rhymes found for "{word}"'})
    for i, t in enumerate(terms):
        t['on'] = i < RHYME_DEFAULT_ON
    return jsonify({'terms': terms, 'word': word, 'error': None})


@app.route('/poetry/rhyme/horses', methods=['POST'])
def poetry_rhyme_horses():
    from flask import jsonify
    data  = request.get_json(silent=True) or {}
    terms = [t for t in (data.get('terms') or []) if isinstance(t, str)]
    if not terms:
        return jsonify({'results': [], 'total': 0})
    results = search_by_rhyme_terms(terms, dictionary)
    return jsonify({'results': results, 'total': len(results)})


@app.route('/poetry/thesaurus/terms', methods=['POST'])
def poetry_thesaurus_terms():
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    word = (data.get('word') or '').strip()
    if not word:
        return jsonify({'terms': [], 'error': 'No word provided'})
    terms = get_synonyms(word)
    if not terms:
        return jsonify({'terms': [], 'error': f'No related words found for "{word}"'})
    for i, t in enumerate(terms):
        t['on'] = i < THESAURUS_DEFAULT_ON
    return jsonify({'terms': terms, 'word': word, 'error': None})


@app.route('/poetry/thesaurus/horses', methods=['POST'])
def poetry_thesaurus_horses():
    from flask import jsonify
    data  = request.get_json(silent=True) or {}
    terms = [t for t in (data.get('terms') or []) if isinstance(t, str)]
    if not terms:
        return jsonify({'results': [], 'total': 0})
    results = search_by_synonym_terms(terms, dictionary)
    return jsonify({'results': results, 'total': len(results)})


@app.route('/poetry/stable/add', methods=['POST'])
@login_required
def stable_add():
    from flask import jsonify
    data   = request.get_json()
    horses = add_to_stable(data['name'], data['display'], data['url'], int(data.get('remaining', 1)))
    return jsonify({'horses': horses})


@app.route('/poetry/stable/remove', methods=['POST'])
@login_required
def stable_remove():
    from flask import jsonify
    data   = request.get_json()
    horses = remove_from_stable(data['name'])
    return jsonify({'horses': horses})


@app.route('/poetry/stable/clear', methods=['POST'])
@login_required
def stable_clear():
    from flask import jsonify
    clear_stable()
    return jsonify({'ok': True})


@app.route('/submissions/post', methods=['POST'])
@login_required
def post_submission():
    """Fast-track: post/queue/draft a submission directly without full review."""
    from flask import jsonify
    if not tumblr.authenticated:
        flash('Not connected to Tumblr', 'err')
        return redirect(url_for('submissions'))

    sub_id = request.form.get('id', '')
    action = request.form.get('action', 'queue')
    sub    = load_submission(sub_id)
    if not sub:
        flash('Submission not found', 'err')
        return redirect(url_for('submissions'))

    horse_count      = sub.get('horse_count', 0)
    stats            = sub.get('stats') or {}
    density          = stats.get('horse_density', 0.0)
    submitter_name   = sub.get('submitter_name', '')
    submitter_tumblr = sub.get('submitter_tumblr', '')
    sub_is_admin     = sub.get('is_admin', False)
    is_user_sub      = not sub_is_admin or bool(submitter_name or submitter_tumblr)

    is_poem = sub.get('type') == 'poem'
    if is_poem:
        pre  = format_poem_prefix(horse_count, sub.get('poem_title', ''), submitter_name, submitter_tumblr)
        mid  = ''
        suf  = POEM_SUFFIX
        tags = ','.join(build_poem_tags(horse_count, submitter_name, submitter_tumblr, is_admin=sub_is_admin))
    else:
        pre  = format_prefix(horse_count, False, density)
        mid  = _attribution_html(submitter_name, submitter_tumblr, prefix='Submitted by')
        suf  = POST_SUFFIX
        name_tag    = f'by {submitter_name}' if submitter_name else ''
        tumblr_tag  = submitter_tumblr if submitter_tumblr else ''
        famous_tags = sub.get('famous_tags', [])
        # Attribution first, then count tags, then famous, then SEO
        attr_parts = [t for t in [
            'user submission' if is_user_sub else '',
            name_tag, tumblr_tag,
        ] if t]
        tags = assemble_tags(
            default_tags=attr_parts + build_default_tags(horse_count, density),
            optional_tags=[],
            custom_tags=','.join(famous_tags),
            seo_tags=SEO_TAGS,
        )

    body = build_post_body(pre, sub.get('linked_html', ''), mid, suf)

    draft = {
        'post_data':    sub.get('post_data', {}),
        'is_text_post': sub.get('is_text_post', False),
        'is_reply':     False,
    }
    success, err = submit_post(
        draft=draft,
        action=action,
        body=body,
        tags=tags,
        make_request=tumblr.make_request,
    )

    if success:
        update_status(sub_id, 'posted')
        action_label = {'post': 'published', 'queue': 'queued', 'draft': 'saved as draft'}.get(action, 'queued')
        flash(f'Post {action_label}!', 'ok')
    else:
        flash(f'Post failed: {err}', 'err')

    return redirect(url_for('submissions'))


# ── Admin: dictionary editor ──────────────────────────────────────────────────

@app.route('/admin/dictionary')
@login_required
def admin_dictionary():
    from matcher import normalize_text
    q = request.args.get('q', '').strip()
    results = []
    error = None
    if q:
        norm = normalize_text(q)
        if len(norm) < 2:
            error = 'Search term must be at least 2 characters after normalisation.'
        else:
            matches = [
                (name, regs)
                for name, regs in dictionary.horses.items()
                if norm in name
            ]
            matches.sort(key=lambda x: (not x[0].startswith(norm), x[0]))
            results = matches[:50]
    return render_template('dictionary_admin.html', q=q, results=results, error=error)


@app.route('/admin/dictionary/set', methods=['POST'])
@login_required
def admin_dictionary_set():
    from matcher import normalize_text
    raw_name = request.form.get('name', '').strip()
    raw_urls = request.form.get('urls', '').strip()
    if not raw_name:
        flash('Name is required.', 'err')
        return redirect(request.referrer or '/admin/dictionary')
    norm = normalize_text(raw_name)
    if not norm:
        flash('Name normalised to empty — check for invalid characters.', 'err')
        return redirect(request.referrer or '/admin/dictionary')
    urls = [u.strip() for u in raw_urls.splitlines() if u.strip()]
    if not urls:
        flash('At least one URL is required.', 'err')
        return redirect(request.referrer or '/admin/dictionary')
    regs = [{'url': u} for u in urls]
    dictionary.override_set(norm, regs)
    flash(f'Saved: {norm} ({len(regs)} registration{"s" if len(regs) != 1 else ""})', 'ok')
    return redirect(f'/admin/dictionary?q={norm}')


@app.route('/admin/dictionary/delete', methods=['POST'])
@login_required
def admin_dictionary_delete():
    name = request.form.get('name', '').strip()
    if not name:
        flash('No name provided.', 'err')
        return redirect(request.referrer or '/admin/dictionary')
    dictionary.override_delete(name)
    flash(f'Deleted: {name}', 'ok')
    q = request.form.get('q', name.split()[0])
    return redirect(f'/admin/dictionary?q={q}')


# ── poet.horse: poem permalink (stub) ─────────────────────────────────────────

@app.route('/p/<short_code>')
def poem_permalink(short_code):
    """
    Public permalink for a poem (Phase 1.5/1.6/1.7).

    Renders title + attribution + optional "After ___" caption + grouped tags
    + Open Graph meta tags. Pasture mode is the permalink default (1.6);
    horse chips are interactive with the popover (1.7).
    """
    from datetime import datetime, timezone

    poem = get_poem_by_short_code(short_code)
    if not poem:
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error=f'No poem found with code "{short_code}"',
        ), 404

    # Visibility gate. Published is public; everything else needs the right
    # eyeballs. Anonymous-author submissions are publicly viewable only after
    # admin publish; the link itself is a soft secret in the meantime.
    user     = g.get('current_user')
    is_admin = bool(session.get('logged_in'))
    if poem['status'] != 'published':
        owns = user is not None and poem.get('author_user_id') == user.get('id')
        if not (is_admin or owns):
            return render_template('index.html',
                horses_loaded=dictionary.loaded,
                active_tab='url',
                form={},
                error=f'No poem found with code "{short_code}"',
            ), 404

    # Group approved tags by category; split into public vs admin-only tiers.
    tag_rows    = tags_for_poem(poem['id'])
    grouped_tags       = []  # public tags — shown to everyone
    grouped_admin_tags = []  # admin-only tags — shown to admins only
    seen_pub, seen_adm = {}, {}
    for r in tag_rows:
        cat_key    = r['cat_id']
        is_adm     = bool(r['admin_only'])
        seen       = seen_adm if is_adm else seen_pub
        group_list = grouped_admin_tags if is_adm else grouped_tags
        if cat_key not in seen:
            seen[cat_key] = {
                'label':    r['cat_label'],
                'behavior': r['behavior'],
                'tags':     [],
            }
            group_list.append(seen[cat_key])
        seen[cat_key]['tags'].append({'slug': r['slug'], 'label': r['label']})

    # For the admin per-poem tag editor, expose all tag categories + which are applied.
    applied_tag_ids = {r['id'] for r in tag_rows}
    editor_pub_cats  = list_categories_with_tags() if _is_admin() else []
    editor_adm_cats  = list_admin_only_categories_with_tags() if _is_admin() else []

    # Open Graph description: first non-empty line's horse list + total count.
    first_line_horses = ''
    for line in poem.get('lines', []):
        if line:
            first_line_horses = ' '.join(h.get('display', '') for h in line)
            break
    n = poem.get('horse_count', 0)
    og_description = (
        f'{first_line_horses} — a {n}-horse poem on poet.horse'
        if first_line_horses else f'A {n}-horse poem on poet.horse'
    )

    published_iso   = ''
    published_human = ''
    if poem.get('published_at'):
        dt = datetime.fromtimestamp(poem['published_at'], tz=timezone.utc)
        published_iso   = dt.isoformat()
        published_human = dt.strftime('%b %-d, %Y') if os.name != 'nt' else dt.strftime('%b %#d, %Y')

    # Page title folds in attribution-to-existing-work: "Title based on Source".
    # Attribution presence is itself the flag — there's no tag for it; the
    # title makes the relationship visible everywhere the title appears
    # (browser tab, og:title, social previews).
    base_title = poem.get('title') or 'A horse poem'
    page_title = (
        f'{base_title} based on {poem["inspired_by_text"]}'
        if poem.get('inspired_by_text') else base_title
    )

    # Enrich each horse with pasture-mode appearance hooks (coat / rev / famous)
    # so the template can render decorated chips without any client-side work.
    # The hooks are inert in plain mode — CSS only acts on them under
    # `[data-view-mode='pasture']`.
    for line in poem.get('lines', []):
        for h in line:
            name = h.get('name', '')
            appearance = horse_appearance(name)
            h['coat']      = appearance['coat']
            h['rev']       = appearance['rev']
            h['is_famous'] = bool(name) and famous_horses.lookup(name) is not None

    # Default view mode for permalinks is pasture (per ROADMAP 1.6). A
    # logged-in user's stored preference overrides; otherwise the client
    # JS may downgrade to plain based on `prefers-reduced-motion` or a
    # localStorage choice. The server passes the chosen default + the
    # known-explicit signal so the template doesn't have to guess.
    server_mode      = None
    if user is not None:
        prefs = get_preferences(user['id'])
        candidate = prefs.get('poem_view_mode')
        if candidate in ('plain', 'pasture'):
            server_mode = candidate

    return render_template(
        'poem.html',
        poem              = poem,
        page_title        = page_title,
        grouped_tags      = grouped_tags,
        grouped_admin_tags = grouped_admin_tags,
        applied_tag_ids   = applied_tag_ids,
        editor_pub_cats   = editor_pub_cats,
        editor_adm_cats   = editor_adm_cats,
        og_description    = og_description,
        permalink_url     = request.url,
        published_iso     = published_iso,
        published_human   = published_human,
        server_view_mode  = server_mode,
    )


# ── poet.horse: admin poem-submissions queue ──────────────────────────────────

@app.route('/admin/poem-queue')
@login_required
def admin_poem_queue():
    pending = load_pending_poem_submissions()
    return render_template('poem_queue.html', submissions=pending)


@app.route('/admin/poem-queue/publish', methods=['POST'])
@login_required
def admin_poem_publish():
    sub_id = int(request.form.get('id', '0') or 0)
    notes  = request.form.get('notes', '').strip()
    poem   = approve_poem_submission(sub_id, reviewer_user_id=None, review_notes=notes)
    if poem:
        flash(f'Published: /p/{poem["short_code"]}', 'ok')
    else:
        flash('Submission not found.', 'err')
    return redirect(url_for('admin_poem_queue'))


@app.route('/admin/poem-queue/reject', methods=['POST'])
@login_required
def admin_poem_reject():
    sub_id = int(request.form.get('id', '0') or 0)
    notes  = request.form.get('notes', '').strip()
    reject_poem_submission(sub_id, reviewer_user_id=None, review_notes=notes)
    flash('Rejected.', 'ok')
    return redirect(url_for('admin_poem_queue'))


# ── Horse collection API ──────────────────────────────────────────────────────

@app.route('/horse/state', methods=['POST'])
def horse_state():
    """
    Return save/pasture state for a list of horse names for the logged-in user.
    POST {names: ["foo", "bar"]}
    Returns {foo: {saved, in_pasture}, bar: {...}}
    Logged-out: all false.
    """
    data  = request.get_json(silent=True) or {}
    names = [n for n in (data.get('names') or []) if isinstance(n, str)][:50]
    user  = g.get('current_user')
    if not user or not names:
        return jsonify({n: {'saved': False, 'in_pasture': False} for n in names})
    states = get_horse_states(user['id'], names)
    return jsonify(states)


@app.route('/horse/save', methods=['POST'])
def horse_save():
    """Toggle blue-ribbon save on a horse. Requires login."""
    user = g.get('current_user')
    if not user:
        return jsonify({'error': 'login_required'}), 401
    data = request.get_json(silent=True) or {}
    name    = (data.get('name') or '').strip()
    display = (data.get('display') or name).strip()
    url     = (data.get('url') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    result = toggle_saved_horse(user['id'], name, display, url)
    return jsonify(result)


@app.route('/horse/pasture', methods=['POST'])
def horse_pasture_toggle():
    """Toggle a horse in/out of the user's pasture. Requires login."""
    user = g.get('current_user')
    if not user:
        return jsonify({'error': 'login_required'}), 401
    data = request.get_json(silent=True) or {}
    name    = (data.get('name') or '').strip()
    display = (data.get('display') or name).strip()
    url     = (data.get('url') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    result = toggle_pasture(user['id'], name, display, url)
    return jsonify(result)


@app.route('/horse/poems', methods=['POST'])
def horse_poems():
    """Return published poems featuring a given horse name (up to 5)."""
    data  = request.get_json(silent=True) or {}
    name  = (data.get('name') or '').strip()
    if not name:
        return jsonify({'poems': []})
    poems = get_poems_featuring_horse(name, limit=5)
    # Trim to what the popover needs — no full lines_json
    result = [
        {
            'short_code':    p['short_code'],
            'title':         p['title'] or '',
            'author':        p['author_display_name'] or '',
            'horse_count':   p['horse_count'],
        }
        for p in poems
    ]
    return jsonify({'poems': result})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=False)
