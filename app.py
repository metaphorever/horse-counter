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

User routes (Clerk login required):
  GET  /me/drafts               draft list page
  POST /me/draft/save           create or update a draft
  GET  /me/draft/list           list drafts for chip picker (JSON)
  POST /me/draft/stable/add     add horse to a draft's stable
  POST /me/draft/delete         delete a draft

Admin routes (login required — Clerk role='admin' OR PIN fallback):
  POST /queue          post/queue/draft a reviewed post
  GET  /auth           start Tumblr OAuth
  GET  /callback       OAuth callback
  GET  /submissions    review pending submissions
  POST /submissions/*  submission actions
  POST /poetry/stable/*  server-persisted stable (admin only)
  GET  /admin/*        admin management pages
  GET  /login          PIN fallback (admin only)
"""

import os
import re
from datetime import datetime, timezone
from flask import (
    Flask, g, request, redirect, session, url_for,
    render_template, flash, jsonify, make_response,
)
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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
    update_profile, set_bio_poem,
    get_user_published_poems, get_user_poems_for_bio_picker,
    update_trust_score, set_trust_score, get_all_users,
    suspend_user, unsuspend_user, delete_user,
)
from db.admin_settings import get_auto_post_threshold, get_setting, set_setting
from db.pasture import add_to_pasture, list_pasture_horses
from db.drafts import (
    list_user_drafts, get_user_draft, save_user_draft,
    add_horse_to_draft_stable, delete_user_draft,
)
from auth import TumblrManager
from matcher import (
    HorseDictionary, ChainCounter,
    find_horses_in_text, render_chain_item, compute_stats,
    horse_appearance,
)
from post_builder import extract_post
from famous import FamousHorses
from db.conn import init_db, get_db
from poem_db import (
    save_poem as save_poem_db,
    get_poem_by_short_code,
    update_poem_status,
    delete_poem,
    list_published as list_published_poems,
    get_poems_featuring_horse,
    browse_poems,
    count_browse_poems,
    get_random_published,
    get_poems_for_tag_slug,
    get_published_poems_by_user,
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
    list_pending_tags,
    approve_tag,
    reject_tag,
    update_tag_label,
    deactivate_tag,
    delete_tag_if_safe,
    update_tag_category,
    delete_tag_category_if_safe,
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
    list_saved_horses,
    remove_from_pasture,
    toggle_saved_poem,
    is_poem_saved,
    list_saved_poems,
)
from db.reports import create_report, list_reports, resolve_report
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

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="memory://",
    default_limits=[],
)

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


# ── Display mode (Phase 1.12) ───────────────────────────────────────────────────
# Three site-wide skins, resolved server-side and emitted as a body class so the
# skin applies on first paint with no JS dependency.
VIEW_MODES        = ('fancy', 'plain', 'reader')
DEFAULT_VIEW_MODE = 'fancy'


def resolve_view() -> tuple[str, bool]:
    """Resolve (display_mode, picker_decided) for this request.

    Mode precedence: signed-in pref -> view_mode cookie -> default fancy.

    `decided` is a *separate* signal from the active mode: whether the visitor
    has saved or dismissed the first-run picker. Keeping them separate lets a
    visitor try modes on (each click sets the active mode) while the picker
    stays open until they explicitly save or dismiss it. Tracked in the
    `view_decided` cookie and mirrored to the account for signed-in users.
    """
    mode    = DEFAULT_VIEW_MODE
    decided = request.cookies.get('view_decided') == '1'

    user  = g.get('current_user')
    prefs = get_preferences(user['id']) if user is not None else {}

    pref_mode = prefs.get('poem_view_mode')
    if pref_mode in VIEW_MODES:
        mode = pref_mode
    else:
        cookie_mode = request.cookies.get('view_mode')
        if cookie_mode in VIEW_MODES:
            mode = cookie_mode

    if prefs.get('view_decided') is True:
        decided = True

    return mode, decided


# Display / reading surfaces — where the skin is most dramatic, and the only
# pages that show the first-run picker strip. Workhorse pages (editor, admin,
# account forms, count, legal) just carry the collapsed nav control.
DISPLAY_SURFACES = frozenset({
    'poem_permalink', 'featured', 'browse', 'random_poem',
    'user_profile', 'me_pasture', 'me_saved_poems', 'me_saved_horses',
})


def is_display_surface() -> bool:
    return request.endpoint in DISPLAY_SURFACES


# ── Template globals ──────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    """Make is_admin, current_user, and Clerk key available in every template."""
    view_mode, picker_decided = resolve_view()
    return {
        'is_admin':              _is_admin(),
        'is_pin_admin':          bool(session.get('logged_in')),
        'current_user':          g.get('current_user'),
        'clerk_publishable_key': CLERK_PUBLISHABLE_KEY,
        'tumblr_auth':           tumblr.authenticated,
        'blog_name':             TUMBLR_BLOG_NAME,
        'view_mode':             view_mode,
        'view_decorated':        view_mode in ('fancy', 'plain'),
        'picker_decided':        picker_decided,
        'display_surface':       is_display_surface(),
        # One-shot confirmation shown in place of the strip right after the
        # visitor saves/dismisses the first-run picker.
        'view_picker_saved':     session.pop('view_picker_saved', False),
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


@app.template_filter('rfc2822')
def rfc2822(ts):
    """Format a Unix timestamp or datetime as RFC 2822 (for RSS <pubDate>)."""
    if isinstance(ts, datetime):
        dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    else:
        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
    return dt.strftime('%a, %d %b %Y %H:%M:%S +0000')


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
            return redirect(url_for('count'))
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
        return redirect(url_for('featured'))
    return render_template('sign_in.html')


@app.route('/sign-out')
def sign_out():
    """Clear the Flask session; page JS will also call Clerk.signOut()."""
    session.clear()
    return render_template('sign_out.html')


@app.route('/auth/clerk/verify', methods=['POST'])
@limiter.limit("20 per minute")
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
        if user.get('suspended_at'):
            return jsonify({'error': 'This account has been suspended.'}), 403
        session.permanent = True
        session['user_id'] = user['id']
        return jsonify({'redirect': url_for('featured')})

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
            return redirect(url_for('featured'))
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
            return redirect(url_for('featured'))

    return render_template('setup_account.html',
        display_name=display_name,
        error=error,
    )


# ── Account sync (Phase 0.5) ──────────────────────────────────────────────────

# Preference keys synced from localStorage. Keep stable names — clients clear
# the matching local keys after a successful sync.
# poem_name and poem_tumblr were removed from the sync path when the attribution
# 3-way chooser replaced the free-text name/Tumblr fields; page_size remains.
_SYNCABLE_PREF_KEYS = ('page_size',)


@app.route('/me/sync', methods=['POST'])
def me_sync():
    """
    Sync anonymous localStorage preferences into the logged-in user's account.

    Body (all fields optional):
        { "page_size": "25" }

    Returns: { ok: true, preferences: {...} }
    """
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Not signed in'}), 401

    body = request.get_json(silent=True) or {}

    pref_updates = {}
    for key in _SYNCABLE_PREF_KEYS:
        if key in body and body[key] not in (None, ''):
            pref_updates[key] = str(body[key])[:80]
    prefs = update_preferences(user['id'], pref_updates) if pref_updates else get_preferences(user['id'])

    return jsonify({'ok': True, 'preferences': prefs})


# Preference keys clients can write through /me/preferences. Allow-listed and
# value-validated below so the endpoint never becomes a free-form key/value
# store on the user row.
_USER_PREF_WRITES = {
    'poem_view_mode':    lambda v: v if v in VIEW_MODES else None,
    'view_decided':      lambda v: True if v is True else None,
    'strip_empty_lines': lambda v: bool(v) if isinstance(v, bool) else None,
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


@app.route('/set-view-mode', methods=['POST'])
def set_view_mode():
    """Set / try the site-wide display mode, and/or decide the first-run picker.

    Works without JavaScript. Two independent form inputs:
      - `mode`   — set the active display mode (a "try it on" click; leaves the
                   first-run picker open so the visitor can keep sampling).
      - `decide` — '1' puts the first-run picker away for good (Save or dismiss);
                   the active mode is whatever was last set.

    Signed-in choices mirror to the account so they follow across devices.
    Redirects back to the originating page (same-site only).
    """
    mode   = request.form.get('mode', '')
    decide = request.form.get('decide') == '1'
    user   = g.get('current_user')

    # Same-site redirect only — never bounce to an absolute or off-site URL.
    nxt = request.form.get('next', '')
    if not (nxt.startswith('/') and not nxt.startswith('//')):
        nxt = '/'
    resp = redirect(nxt)

    one_year = 60 * 60 * 24 * 365
    if mode in VIEW_MODES:
        resp.set_cookie('view_mode', mode, max_age=one_year, samesite='Lax')
        if user is not None:
            update_preferences(user['id'], {'poem_view_mode': mode})
    if decide:
        resp.set_cookie('view_decided', '1', max_age=one_year, samesite='Lax')
        if user is not None:
            update_preferences(user['id'], {'view_decided': True})
        session['view_picker_saved'] = True
    return resp


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
    """Public poet profile — Phase 1.15."""
    import json as _json
    user = get_user_by_slug(slug)
    if not user:
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error=f'No poet found with the slug "{slug}"',
        ), 404
    user = dict(user)
    try:
        user['links'] = _json.loads(user.get('links_json') or '[]')
    except (TypeError, ValueError):
        user['links'] = []
    poems = get_published_poems_by_user(user['id'])
    bio_poem = None
    if user.get('bio_poem_id'):
        from poem_db import get_poem_by_id as _get_poem_by_id
        bio_poem = _get_poem_by_id(user['bio_poem_id'])
        if bio_poem and bio_poem.get('status') != 'published':
            bio_poem = None
        if bio_poem:
            for line in bio_poem.get('lines', []):
                for h in line:
                    name = h.get('name', '')
                    app_ = horse_appearance(name)
                    h['coat'] = app_['coat']
                    h['rev']  = app_['rev']
                    h['is_famous'] = bool(name) and famous_horses.lookup(name) is not None
    bio_picker_poems = []
    is_own_profile = (g.get('current_user') or {}).get('id') == user['id']
    if is_own_profile:
        bio_picker_poems = get_user_poems_for_bio_picker(user['id'])
    return render_template('user_profile.html',
        poet=user,
        poems=poems,
        bio_poem=bio_poem,
        bio_picker_poems=bio_picker_poems,
        is_own_profile=is_own_profile,
    )


# ── Public browse / discover stubs (Phase 1.1) ───────────────────────────────

@app.route('/feed.xml')
def rss_feed():
    poems = browse_poems(sort='newest', per_page=50)
    now = datetime.now(tz=timezone.utc)
    xml = render_template('feed.xml', poems=poems, now=now)
    resp = make_response(xml)
    resp.headers['Content-Type'] = 'application/rss+xml; charset=utf-8'
    return resp


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


# ── Admin: featured sections + tag management (Phase 1.8 / 1.4) ──────────────

@app.route('/admin/featured')
@login_required
def admin_featured():
    sections      = list_all_featured_sections()
    admin_cats    = list_admin_only_categories_with_tags()
    all_cats      = list_all_categories_with_tags()
    pending_tags  = list_pending_tags()
    return render_template(
        'admin_featured.html',
        sections      = sections,
        admin_cats    = admin_cats,
        all_cats      = all_cats,
        pending_tags  = pending_tags,
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


@app.route('/admin/tag/<int:tag_id>/approve', methods=['POST'])
@login_required
def admin_tag_approve(tag_id):
    if approve_tag(tag_id):
        flash('Tag approved and activated.', 'success')
    else:
        flash('Tag not found or already reviewed.', 'error')
    return redirect(url_for('admin_featured'))


@app.route('/admin/tag/<int:tag_id>/reject', methods=['POST'])
@login_required
def admin_tag_reject(tag_id):
    if reject_tag(tag_id):
        flash('Tag suggestion rejected.', 'success')
    else:
        flash('Tag not found or already reviewed.', 'error')
    return redirect(url_for('admin_featured'))


@app.route('/admin/tag/<int:tag_id>/update', methods=['POST'])
@login_required
def admin_tag_update(tag_id):
    label = (request.form.get('label') or '').strip()
    if update_tag_label(tag_id, label):
        flash(f'Tag renamed to "{label}".', 'success')
    else:
        flash('Could not rename — label is invalid or already exists in this category.', 'error')
    return redirect(url_for('admin_featured'))


@app.route('/admin/tag/<int:tag_id>/deactivate', methods=['POST'])
@login_required
def admin_tag_deactivate(tag_id):
    if deactivate_tag(tag_id):
        flash('Tag deactivated (hidden from pickers; existing poem tags preserved).', 'success')
    else:
        flash('Tag not found or already inactive.', 'error')
    return redirect(url_for('admin_featured'))


@app.route('/admin/tag/<int:tag_id>/delete', methods=['POST'])
@login_required
def admin_tag_delete(tag_id):
    if delete_tag_if_safe(tag_id):
        flash('Tag deleted.', 'success')
    else:
        flash('Tag is referenced by poems and cannot be deleted. Deactivate it instead.', 'error')
    return redirect(url_for('admin_featured'))


@app.route('/admin/tag-category/<int:cat_id>/update', methods=['POST'])
@login_required
def admin_tag_category_update(cat_id):
    label      = (request.form.get('label') or '').strip() or None
    behavior   = request.form.get('behavior') or None
    admin_only = request.form.get('admin_only', '0') == '1'
    try:
        sort_order = int(request.form['sort_order']) if 'sort_order' in request.form else None
    except (ValueError, TypeError):
        sort_order = None
    if update_tag_category(cat_id, label=label, behavior=behavior,
                           sort_order=sort_order, admin_only=admin_only):
        flash('Category updated.', 'success')
    else:
        flash('Could not update category — invalid input.', 'error')
    return redirect(url_for('admin_featured'))


@app.route('/admin/tag-category/<int:cat_id>/delete', methods=['POST'])
@login_required
def admin_tag_category_delete(cat_id):
    if delete_tag_category_if_safe(cat_id):
        flash('Category deleted.', 'success')
    else:
        flash('Category still has tags — remove all tags first.', 'error')
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
    user = g.get('current_user')
    return redirect(url_for('user_profile', slug=user['slug']))


@app.route('/me/drafts')
@user_required
def me_drafts():
    import json
    user = g.get('current_user')
    drafts = list_user_drafts(user['id'])
    # Parse line counts for display without exposing full JSON to template
    for d in drafts:
        try:
            lines = json.loads(d.get('lines_json') or '[]')
            d['horse_count'] = sum(len(l) for l in lines if isinstance(l, list))
        except Exception:
            d['horse_count'] = 0
    return render_template('me_drafts.html', drafts=drafts)


@app.route('/me/draft/save', methods=['POST'])
def me_draft_save():
    """Create or update a user draft.

    Body: { draft_id?, title, lines_json, stable_json,
            submitter_name, submitter_tumblr,
            inspired_by_text, inspired_by_url, tag_ids_json }
    Returns: { ok: true, draft: {id, title, updated_at} }
    """
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Sign in to save drafts'}), 401

    body      = request.get_json(silent=True) or {}
    draft_id  = body.get('draft_id') or None
    if draft_id:
        try:
            draft_id = int(draft_id)
        except (TypeError, ValueError):
            draft_id = None

    title     = (body.get('title') or '').strip()[:120]
    lines_raw = body.get('lines_json') or '[]'
    stable_raw = body.get('stable_json') or '[]'

    # Validate JSON blobs client sent
    import json as _json
    try:
        _json.loads(lines_raw)
    except Exception:
        lines_raw = '[]'
    try:
        _json.loads(stable_raw)
    except Exception:
        stable_raw = '[]'
    tag_raw = body.get('tag_ids_json') or '[]'
    try:
        _json.loads(tag_raw)
    except Exception:
        tag_raw = '[]'

    raw_post_as = (body.get('post_as') or 'account').strip()
    if raw_post_as not in ('account', 'anonymous', 'pseudonymous'):
        raw_post_as = 'account'

    draft = save_user_draft(
        user_id         = user['id'],
        draft_id        = draft_id,
        title           = title,
        lines_json      = lines_raw,
        stable_json     = stable_raw,
        submitter_name  = (body.get('submitter_name')  or '').strip()[:60],
        submitter_tumblr= (body.get('submitter_tumblr') or '').strip()[:32],
        inspired_by_text= (body.get('inspired_by_text') or '').strip()[:200],
        inspired_by_url = (body.get('inspired_by_url')  or '').strip()[:300],
        tag_ids_json    = tag_raw,
        post_as         = raw_post_as,
    )
    return jsonify({'ok': True, 'draft': {
        'id':         draft['id'],
        'title':      draft['title'],
        'updated_at': draft['updated_at'],
    }})


@app.route('/me/draft/list', methods=['GET', 'POST'])
def me_draft_list():
    """Return the current user's drafts for the chip picker and editor picker.

    Returns [{id, title, horse_count, updated_at}, ...] newest first.
    horse_count is the number of horses in the draft's stable.
    """
    import json as _json
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Not signed in'}), 401
    drafts = list_user_drafts(user['id'])
    result = []
    for d in drafts:
        try:
            stable = _json.loads(d.get('stable_json') or '[]')
            horse_count = len(stable) if isinstance(stable, list) else 0
        except Exception:
            horse_count = 0
        result.append({
            'id':          d['id'],
            'title':       d['title'],
            'horse_count': horse_count,
            'updated_at':  d['updated_at'],
        })
    return jsonify({'ok': True, 'drafts': result})


@app.route('/me/draft/get', methods=['GET'])
def me_draft_get():
    """Return a single draft's full JSON.

    Query param: ?id=<draft_id>
    Returns the full draft row including lines_json, stable_json, and all metadata.
    """
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Not signed in'}), 401
    try:
        draft_id = int(request.args.get('id', ''))
    except (TypeError, ValueError):
        return jsonify({'error': 'id required'}), 400
    draft = get_user_draft(draft_id, user['id'])
    if draft is None:
        return jsonify({'error': 'Draft not found'}), 404
    return jsonify({'ok': True, 'draft': draft})


@app.route('/me/draft/create', methods=['POST'])
def me_draft_create():
    """Create a new draft and optionally add one horse to its stable.

    Body: { title?, horse_name?, horse_display?, horse_url? }
    Returns: { ok: true, draft: {id, title} }
    """
    import json as _json
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Not signed in'}), 401
    body    = request.get_json(silent=True) or {}
    title   = (body.get('title') or '').strip()[:120]
    name    = (body.get('horse_name')    or '').strip()[:200]
    display = (body.get('horse_display') or name).strip()[:200]
    url     = (body.get('horse_url')     or '').strip()[:500]

    stable_data = []
    if name:
        stable_data = [{'name': name, 'display': display, 'url': url, 'remaining': 1}]

    draft = save_user_draft(
        user_id      = user['id'],
        draft_id     = None,
        title        = title,
        lines_json   = '[[]]',
        stable_json  = _json.dumps(stable_data),
    )
    return jsonify({'ok': True, 'draft': {'id': draft['id'], 'title': draft['title']}})


@app.route('/me/draft/stable/add', methods=['POST'])
def me_draft_stable_add():
    """Add one horse to a specific draft's stable.

    Body: { draft_id: int, name, display, url }
    Returns: { ok: true, added: bool }
    """
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Not signed in'}), 401
    body = request.get_json(silent=True) or {}
    try:
        draft_id = int(body.get('draft_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'draft_id required'}), 400
    name    = (body.get('name')    or '').strip()[:200]
    display = (body.get('display') or name).strip()[:200]
    url     = (body.get('url')     or '').strip()[:500]
    if not name:
        return jsonify({'error': 'name required'}), 400
    added = add_horse_to_draft_stable(draft_id, user['id'], name, display, url)
    return jsonify({'ok': True, 'added': added})


@app.route('/me/draft/delete', methods=['POST'])
def me_draft_delete():
    """Delete a user draft.

    Body: { draft_id: int }
    Returns: { ok: true }
    """
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Not signed in'}), 401
    body = request.get_json(silent=True) or {}
    try:
        draft_id = int(body.get('draft_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'draft_id required'}), 400
    delete_user_draft(draft_id, user['id'])
    return jsonify({'ok': True})


@app.route('/me/pasture')
@user_required
def me_pasture():
    """Phase 1.19 — pasture horse list."""
    user = g.get('current_user')
    horses = list_pasture_horses(user['id'])
    for h in horses:
        name = h.get('name', '')
        app_ = horse_appearance(name)
        h['coat'] = app_['coat']
        h['rev']  = app_['rev']
        h['is_famous'] = bool(name) and famous_horses.lookup(name) is not None
    return render_template('my_pasture.html', horses=horses)


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


@app.route('/me/pasture/remove', methods=['POST'])
@user_required
def me_pasture_remove():
    """Remove one horse from the user's pasture by name."""
    user = g.get('current_user')
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    remove_from_pasture(user['id'], name)
    return jsonify({'ok': True})


@app.route('/me/saved-poems')
@user_required
def me_saved_poems():
    """Phase 1.19 — saved poem list."""
    user = g.get('current_user')
    poems = list_saved_poems(user['id'])
    return render_template('saved_poems.html', poems=poems)


@app.route('/me/saved-horses')
@user_required
def me_saved_horses():
    """Phase 1.19 — saved (ribbon) horse list."""
    user = g.get('current_user')
    horses = list_saved_horses(user['id'])
    for h in horses:
        name = h.get('name', '')
        app_ = horse_appearance(name)
        h['coat'] = app_['coat']
        h['rev']  = app_['rev']
        h['is_famous'] = bool(name) and famous_horses.lookup(name) is not None
    return render_template('saved_horses.html', horses=horses)


@app.route('/me/profile', methods=['GET'])
@user_required
def me_profile():
    """Phase 1.15 — edit profile form."""
    import json as _json
    user = g.get('current_user')
    try:
        links = _json.loads(user.get('links_json') or '[]')
    except (TypeError, ValueError):
        links = []
    bio_poem = None
    if user.get('bio_poem_id'):
        from poem_db import get_poem_by_id as _get_poem_by_id
        bio_poem = _get_poem_by_id(user['bio_poem_id'])
        if bio_poem and bio_poem.get('status') != 'published':
            bio_poem = None
    bio_picker_poems = get_user_poems_for_bio_picker(user['id'])
    return render_template('profile_edit.html',
                           profile_links=links,
                           bio_poem=bio_poem,
                           bio_picker_poems=bio_picker_poems)


@app.route('/me/profile/save', methods=['POST'])
@user_required
def me_profile_save():
    """Phase 1.15 — save display_name + links."""
    import json as _json
    user = g.get('current_user')
    display_name = request.form.get('display_name', '').strip()[:80]
    labels = request.form.getlist('link_label[]')
    urls   = request.form.getlist('link_url[]')
    links  = [
        {'label': lbl.strip()[:80], 'url': u.strip()[:500]}
        for lbl, u in zip(labels, urls)
        if u.strip()
    ]
    update_profile(user['id'], display_name or user['display_name'], links)
    flash('Profile saved.', 'ok')
    return redirect(url_for('me_profile'))


@app.route('/me/profile/bio', methods=['POST'])
@user_required
def me_profile_bio():
    """Phase 1.15 — set or clear the bio poem."""
    user = g.get('current_user')
    data = request.get_json(silent=True) or {}
    raw = data.get('poem_id')
    if raw is None or raw == '':
        set_bio_poem(user['id'], None)
        return jsonify({'ok': True, 'cleared': True})
    try:
        poem_id = int(raw)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid poem_id'}), 400
    from poem_db import get_poem_by_id as _get_poem_by_id
    poem = _get_poem_by_id(poem_id)
    if not poem or poem.get('author_user_id') != user['id']:
        return jsonify({'error': 'not found'}), 404
    set_bio_poem(user['id'], poem_id)
    return jsonify({'ok': True, 'poem_id': poem_id})


# ── Homepage ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('featured'))


# ── Horse counter ─────────────────────────────────────────────────────────────

@app.route('/count', methods=['GET', 'POST'])
def count():
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
        return redirect(url_for('count'))

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
@limiter.limit("10 per minute")
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
@limiter.limit("10 per minute")
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

    poem_title       = _sanitize_name(data.get('poem_title', ''))
    submitter_link   = (data.get('submitter_link') or '').strip()[:300]
    submitter_tumblr = _sanitize_tumblr(data.get('submitter_tumblr', ''))
    inspired_text    = (data.get('inspired_by_text') or '').strip()[:300]
    inspired_url     = (data.get('inspired_by_url')  or '').strip()[:300]
    raw_tag_ids      = data.get('tag_ids') or []

    # Attribution: 3-way chooser — account / anonymous / pseudonymous.
    # Legacy clients omit post_as; treat as 'account' when logged in, else anonymous.
    post_as = (data.get('post_as') or '').strip()
    if post_as not in ('account', 'anonymous', 'pseudonymous'):
        post_as = 'account'

    current_user = g.get('current_user')

    if post_as == 'account' and current_user:
        author_user_id      = current_user['id']
        author_display_name = current_user.get('display_name') or current_user.get('slug', '')
        author_link_url     = f'/u/{current_user["slug"]}'
    elif post_as == 'pseudonymous':
        author_user_id      = None
        author_display_name = _sanitize_name(data.get('submitter_name', ''))
        author_link_url     = submitter_link or (
            f'https://www.tumblr.com/{submitter_tumblr}' if submitter_tumblr else ''
        )
    else:
        # anonymous (or 'account' but not logged in — fall back gracefully)
        author_user_id      = None
        author_display_name = ''
        author_link_url     = ''

    tag_ids = []
    if isinstance(raw_tag_ids, list):
        for t in raw_tag_ids[:40]:  # generous cap; helper revalidates against DB
            try:
                tag_ids.append(int(t))
            except (TypeError, ValueError):
                continue

    # Check if this user qualifies to bypass the submission queue.
    threshold = get_auto_post_threshold()
    bypass_queue = (
        post_as == 'account'
        and current_user is not None
        and not current_user.get('suspended_at')
        and threshold is not None
        and current_user.get('trust_score', 0) >= threshold
    )

    poem_status = 'published' if bypass_queue else 'submitted'
    poem = save_poem_db(
        lines               = lines,
        title               = poem_title,
        author_user_id      = author_user_id,
        author_display_name = author_display_name,
        author_link_url     = author_link_url,
        inspired_by_text    = inspired_text,
        inspired_by_url     = inspired_url,
        status              = poem_status,
    )

    if bypass_queue:
        # Publish directly — apply tags as approved, no submission row needed.
        if tag_ids:
            apply_tags_to_poem(poem['id'], tag_ids, applied_by=author_user_id, status='approved')
        return jsonify({
            'ok':         True,
            'message':    'Poem published!',
            'short_code': poem['short_code'],
            'published':  True,
        })

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
        return redirect(url_for('count'))

    return render_template('index.html',
        horses_loaded=dictionary.loaded, active_tab='url', form={},
        error='Auth failed: could not exchange code for token',
    )


# ── Poetry editor ─────────────────────────────────────────────────────────────

@app.route('/poetry')
def poetry_editor():
    import json
    is_admin = bool(session.get('logged_in'))
    initial_draft  = None
    initial_drafts = []
    if is_admin:
        stable = load_stable()
        prefs  = {}
    elif g.get('current_user'):
        # 1.27: stable is no longer server-persisted continuously; it lives in
        # the draft. Start from empty; the client restores from a saved draft
        # or stays empty. Anonymous users hydrate from horse-draft localStorage.
        stable = []
        prefs  = get_preferences(g.current_user['id'])
        # If ?draft=<id> is in the URL (e.g. "Resume editing" from /me/drafts),
        # load that draft and pass it to the template so the editor boots with
        # the right stable/lines already populated.
        draft_param = request.args.get('draft')
        if draft_param:
            try:
                initial_draft = get_user_draft(int(draft_param), g.current_user['id'])
            except (ValueError, TypeError):
                pass
        # 1.28: pass the draft list so the page-load picker can render without
        # a client-side round trip. Only needed when no specific draft was requested.
        if initial_draft is None:
            all_drafts = list_user_drafts(g.current_user['id'])
            initial_drafts = []
            for d in all_drafts:
                try:
                    stable_data = json.loads(d.get('stable_json') or '[]')
                    hc = len(stable_data) if isinstance(stable_data, list) else 0
                except Exception:
                    hc = 0
                initial_drafts.append({
                    'id': d['id'], 'title': d['title'],
                    'horse_count': hc, 'updated_at': d['updated_at'],
                })
        else:
            initial_drafts = []
    else:
        stable = []
        prefs  = {}
        initial_drafts = []
    tag_categories = list_categories_with_tags()
    return render_template('poetry.html',
        stable_json=json.dumps(stable),
        user_prefs_json=json.dumps(prefs),
        optional_tags_json=json.dumps(OPTIONAL_TAGS),
        tag_categories_json=json.dumps(tag_categories),
        initial_draft_json=json.dumps(initial_draft),
        initial_drafts_json=json.dumps(initial_drafts),
    )


@app.route('/poetry/search', methods=['POST'])
@limiter.limit("60 per minute")
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
    n    = min(int(data.get('n', 5)), 50)
    return jsonify({'ok': True, 'results': random_horses(dictionary, n)})


@app.route('/poetry/pasture-horses', methods=['POST'])
def poetry_pasture_horses():
    from flask import jsonify
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Sign in to browse your pasture'}), 401
    horses = list_pasture_horses(user['id'])
    horses.sort(key=lambda h: (h.get('display') or h['name']).lower())
    for h in horses:
        h.setdefault('count', 1)
    return jsonify({'ok': True, 'results': horses})


@app.route('/poetry/saved-horses', methods=['POST'])
def poetry_saved_horses():
    from flask import jsonify
    user = g.get('current_user')
    if user is None:
        return jsonify({'error': 'Sign in to browse your saved horses'}), 401
    horses = list_saved_horses(user['id'])
    horses.sort(key=lambda h: (h.get('display') or h['name']).lower())
    for h in horses:
        h.setdefault('count', 1)
    return jsonify({'ok': True, 'results': horses})


@app.route('/poetry/short', methods=['POST'])
def poetry_short():
    from flask import jsonify
    results = short_horses(dictionary)
    return jsonify({'ok': True, 'results': results, 'total': len(results)})


@app.route('/poetry/rhyme/terms', methods=['POST'])
@limiter.limit("60 per minute")
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
@limiter.limit("60 per minute")
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
@limiter.limit("60 per minute")
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
    # Include pending tags in the checked set so the admin sees submitted tag
    # choices pre-selected rather than empty; saving converts them to approved.
    applied_tag_ids = {r['id'] for r in tag_rows}
    if _is_admin():
        with get_db() as _conn:
            _pending = _conn.execute(
                "SELECT tag_id FROM poem_tags WHERE poem_id = ? AND status = 'pending'",
                (poem['id'],),
            ).fetchall()
        applied_tag_ids |= {r['tag_id'] for r in _pending}
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

    # Enrich each horse with appearance hooks (coat / rev / famous) so the
    # template can render decorated chips without any client-side work. The
    # hooks are inert except in Fancy mode — CSS only acts on them under the
    # server-emitted `body.view-fancy` class.
    # Also cycle through dictionary registrations for repeated names so each
    # occurrence in the poem gets a distinct URL instead of all pointing at
    # the first registration.
    name_counters: dict = {}
    for line in poem.get('lines', []):
        for h in line:
            name = h.get('name', '')
            appearance = horse_appearance(name)
            h['coat']      = appearance['coat']
            h['rev']       = appearance['rev']
            h['is_famous'] = bool(name) and famous_horses.lookup(name) is not None
            if name:
                idx = name_counters.get(name, 0)
                name_counters[name] = idx + 1
                regs = dictionary.horses.get(name)
                if regs and len(regs) > 1:
                    h['url'] = regs[idx % len(regs)]['url']

    cur_user = g.get('current_user')
    poem_saved = False
    if cur_user:
        poem_saved = is_poem_saved(cur_user['id'], poem['id'])

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
        permalink_url     = f'https://poet.horse/p/{short_code}',
        published_iso     = published_iso,
        published_human   = published_human,
        poem_saved        = poem_saved,
    )


# ── Poem report (Phase 1.14) ──────────────────────────────────────────────────

@app.route('/p/<short_code>/report', methods=['POST'])
@limiter.limit("3 per hour")
def poem_report(short_code):
    poem = get_poem_by_short_code(short_code)
    if not poem or poem.get('status') != 'published':
        return jsonify({'error': 'not found'}), 404
    data = request.get_json(silent=True) or {}
    reason = (request.form.get('reason') or data.get('reason') or '').strip()[:500]
    if not reason:
        return jsonify({'error': 'reason required'}), 400
    user = g.get('current_user')
    create_report(
        target_type='poem',
        target_id=poem['id'],
        reason=reason,
        reporter_user_id=user['id'] if user else None,
        reporter_ip=request.remote_addr or '',
    )
    if request.is_json:
        return jsonify({'ok': True})
    flash('Thank you — this poem has been reported.', 'ok')
    return redirect(url_for('poem_permalink', short_code=short_code))


# ── Poem save / ribbon (Phase 1.19) ───────────────────────────────────────────

@app.route('/p/<short_code>/save', methods=['POST'])
def poem_save_toggle(short_code):
    """Toggle the blue-ribbon save for the current user on a poem."""
    user = g.get('current_user')
    if not user:
        return jsonify({'error': 'login_required'}), 401
    poem = get_poem_by_short_code(short_code)
    if not poem or poem.get('status') != 'published':
        return jsonify({'error': 'not found'}), 404
    result = toggle_saved_poem(user['id'], poem['id'])
    return jsonify(result)


# ── Admin: report queue (Phase 1.14) ─────────────────────────────────────────

@app.route('/admin/reports')
@login_required
def admin_reports():
    status = request.args.get('status', 'pending')
    if status not in ('pending', 'actioned', 'dismissed', 'all'):
        status = 'pending'
    reports = list_reports(status)
    return render_template('admin_reports.html', reports=reports, status_filter=status)


@app.route('/admin/report/<int:report_id>/action', methods=['POST'])
@login_required
def admin_report_action(report_id):
    action = request.form.get('action') or (request.get_json(silent=True) or {}).get('action')
    if action not in ('actioned', 'dismissed'):
        flash('Invalid action.', 'err')
        return redirect(url_for('admin_reports'))
    user = g.get('current_user')
    resolve_report(report_id, action, user['id'] if user else 0)
    flash(f'Report {action}.', 'ok')
    return redirect(url_for('admin_reports'))


# ── poet.horse: admin poem-submissions queue ──────────────────────────────────

@app.route('/admin/poem-queue')
@login_required
def admin_poem_queue():
    pending = load_pending_poem_submissions()

    # Enrich horse chips with appearance data
    for sub in pending:
        for line in sub.get('lines', []):
            for h in line:
                name = h.get('name', '')
                appearance = horse_appearance(name)
                h['coat']      = appearance['coat']
                h['rev']       = appearance['rev']
                h['is_famous'] = bool(name) and famous_horses.lookup(name) is not None

    # Attach pending tags per submission for the collapsed chip view
    with get_db() as conn:
        for sub in pending:
            rows = conn.execute(
                """SELECT pt.tag_id, t.label AS tag_label, t.slug AS tag_slug
                     FROM poem_tags pt
                     JOIN tags t ON t.id = pt.tag_id
                    WHERE pt.poem_id = ? AND pt.status = 'pending'
                    ORDER BY t.label COLLATE NOCASE""",
                (sub['id'],),
            ).fetchall()
            sub['pending_tags']    = [dict(r) for r in rows]
            sub['pending_tag_ids'] = {r['tag_id'] for r in rows}

    all_tag_cats = list_all_categories_with_tags()
    return render_template('poem_queue.html', submissions=pending, all_tag_cats=all_tag_cats)


@app.route('/admin/poem-queue/publish', methods=['POST'])
@login_required
def admin_poem_publish():
    sub_id  = int(request.form.get('id', '0') or 0)
    notes   = request.form.get('notes', '').strip()
    tag_ids = [int(x) for x in request.form.getlist('tag_ids') if x.strip().isdigit()]

    sub = load_poem_submission(sub_id)
    if not sub:
        flash('Submission not found.', 'err')
        return redirect(url_for('admin_poem_queue'))

    current_user = g.get('current_user')
    reviewer_id  = current_user['id'] if current_user else None

    # Capture original pending tags before we replace them, to detect edits.
    with get_db() as conn:
        orig_rows = conn.execute(
            "SELECT tag_id FROM poem_tags WHERE poem_id = ? AND status = 'pending'",
            (sub['id'],),
        ).fetchall()
    original_tag_ids = {r['tag_id'] for r in orig_rows}
    tags_edited = set(tag_ids) != original_tag_ids

    # Replace all tags (pending + approved) with admin's explicit selection
    with get_db() as conn:
        conn.execute("DELETE FROM poem_tags WHERE poem_id = ?", (sub['id'],))
    if tag_ids:
        apply_tags_to_poem(sub['id'], tag_ids, applied_by=reviewer_id, status='approved')

    poem = approve_poem_submission(sub_id, reviewer_user_id=reviewer_id, review_notes=notes)
    if poem:
        # Update author's trust score: +1 if tags were untouched, -1 if admin edited them.
        author_id = sub.get('author_user_id')
        if author_id:
            delta = -1 if tags_edited else 1
            update_trust_score(author_id, delta)
        flash(f'Published: /p/{poem["short_code"]}', 'ok')
    else:
        flash('Submission not found.', 'err')
    return redirect(url_for('admin_poem_queue'))


@app.route('/admin/poem-queue/reject', methods=['POST'])
@login_required
def admin_poem_reject():
    sub_id = int(request.form.get('id', '0') or 0)
    notes  = request.form.get('notes', '').strip()
    current_user = g.get('current_user')
    reviewer_id  = current_user['id'] if current_user else None
    reject_poem_submission(sub_id, reviewer_user_id=reviewer_id, review_notes=notes)
    flash('Rejected.', 'ok')
    return redirect(url_for('admin_poem_queue'))


# ── Admin user management ─────────────────────────────────────────────────────

@app.route('/admin/users')
@login_required
def admin_users():
    users = get_all_users()
    threshold = get_setting('auto_post_threshold', '0')
    return render_template('admin_users.html', users=users, threshold=threshold)


@app.route('/admin/users/threshold', methods=['POST'])
@login_required
def admin_set_threshold():
    raw = request.form.get('threshold', '').strip()
    # Allow '' (disabled) or a non-negative integer.
    if raw == '':
        set_setting('auto_post_threshold', '')
        flash('Auto-post disabled — all submissions go to the queue.', 'ok')
    else:
        try:
            val = int(raw)
            if val < 0:
                raise ValueError
        except ValueError:
            flash('Threshold must be a non-negative integer or blank (disabled).', 'err')
            return redirect(url_for('admin_users'))
        set_setting('auto_post_threshold', str(val))
        flash(f'Auto-post threshold set to {val}.', 'ok')
    return redirect(url_for('admin_users'))


@app.route('/admin/user/<int:user_id>')
@login_required
def admin_user_detail(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'err')
        return redirect(url_for('admin_users'))
    poems = get_user_published_poems(user_id)
    return render_template('admin_user_detail.html', user=user, poems=poems)


@app.route('/admin/user/<int:user_id>/trust', methods=['POST'])
@login_required
def admin_set_user_trust(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'err')
        return redirect(url_for('admin_users'))
    raw = request.form.get('trust_score', '').strip()
    try:
        score = int(raw)
    except ValueError:
        flash('Trust score must be an integer.', 'err')
        return redirect(url_for('admin_user_detail', user_id=user_id))
    set_trust_score(user_id, score)
    flash(f'Trust score set to {score}.', 'ok')
    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/user/<int:user_id>/suspend', methods=['POST'])
@login_required
def admin_user_suspend(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'err')
        return redirect(url_for('admin_users'))
    if user.get('role') == 'admin':
        flash('Cannot suspend an admin account.', 'err')
        return redirect(url_for('admin_user_detail', user_id=user_id))
    suspend_user(user_id)
    flash('Account suspended.', 'ok')
    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/user/<int:user_id>/unsuspend', methods=['POST'])
@login_required
def admin_user_unsuspend(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'err')
        return redirect(url_for('admin_users'))
    unsuspend_user(user_id)
    flash('Account reinstated.', 'ok')
    return redirect(url_for('admin_user_detail', user_id=user_id))


@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_user_delete(user_id):
    user = get_user_by_id(user_id)
    if not user:
        flash('User not found.', 'err')
        return redirect(url_for('admin_users'))
    if user.get('role') == 'admin':
        flash('Cannot delete an admin account.', 'err')
        return redirect(url_for('admin_user_detail', user_id=user_id))
    delete_user(user_id)
    flash('Account deleted. Their poems are now anonymous.', 'ok')
    return redirect(url_for('admin_users'))


# ── Admin poem actions ───────────────────────────────────────────────────────

@app.route('/admin/poem/<short_code>/hide', methods=['POST'])
@login_required
def admin_poem_hide(short_code):
    poem = get_poem_by_short_code(short_code)
    if not poem:
        flash('Poem not found.', 'err')
        return redirect(url_for('admin_poem_queue'))
    update_poem_status(poem['id'], 'hidden')
    flash('Poem hidden.', 'ok')
    return redirect(url_for('poem_permalink', short_code=short_code))


@app.route('/admin/poem/<short_code>/unhide', methods=['POST'])
@login_required
def admin_poem_unhide(short_code):
    poem = get_poem_by_short_code(short_code)
    if not poem:
        flash('Poem not found.', 'err')
        return redirect(url_for('admin_poem_queue'))
    update_poem_status(poem['id'], 'published')
    flash('Poem restored to published.', 'ok')
    return redirect(url_for('poem_permalink', short_code=short_code))


@app.route('/admin/poem/<short_code>/delete', methods=['POST'])
@login_required
def admin_poem_delete(short_code):
    poem = get_poem_by_short_code(short_code)
    if not poem:
        flash('Poem not found.', 'err')
        return redirect(url_for('admin_poem_queue'))
    poem_id = poem['id']
    delete_poem(poem_id)
    flash('Poem permanently deleted.', 'ok')
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
