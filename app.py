"""
app.py - Flask routes for Horse Counter

Public routes (no login required):
  GET  /               main input page (URL + text tabs)
  POST /               process URL or text, show count + submit option
  POST /submit         save a counted post submission (public or admin)
  POST /submit/poem    save a poem submission (public or admin)
  GET  /poetry         poetry editor
  POST /poetry/search  horse name search

Admin routes (login required):
  POST /               reply mode
  POST /queue          post/queue/draft a reviewed post
  GET  /auth           start Tumblr OAuth
  GET  /callback       OAuth callback
  GET  /submissions    review pending submissions
  POST /submissions/approve  move a submission to the review page
  POST /submissions/post     fast-track post/queue/draft from queue
  POST /submissions/reject   discard a submission
  POST /poetry/stable/*      server-persisted stable (admin only)
"""

import os
import re
from datetime import datetime
from flask import (
    Flask, request, redirect, session, url_for,
    render_template, flash
)
from functools import wraps

from config import (
    SECRET_KEY, SESSION_LIFETIME_SECONDS,
    TUMBLR_BLOG_NAME, HORSES_RICH_FILE, HORSES_LEGACY_FILE, HORSE_OVERRIDES_FILE,
    FAMOUS_HORSES_FILE,
    check_pin, get_horse_emoji, build_default_tags,
    OPTIONAL_TAGS, POST_SUFFIX, SEO_TAGS, format_prefix,
)
from auth import TumblrManager
from matcher import (
    HorseDictionary, ChainCounter,
    find_horses_in_text, render_chain_item, compute_stats,
)
from post_builder import extract_post
from famous import FamousHorses
from poem_db import save_poem as save_poem_db, get_poem_by_short_code, list_published as list_published_poems
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

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = SESSION_LIFETIME_SECONDS

# ── Initialise singletons ─────────────────────────────────────────────────────

print("Initialising Horse Counter...")
dictionary     = HorseDictionary(HORSES_RICH_FILE, HORSES_LEGACY_FILE, HORSE_OVERRIDES_FILE)
famous_horses  = FamousHorses(FAMOUS_HORSES_FILE)
tumblr         = TumblrManager()
print(f"Ready. Dictionary: {dictionary.source}, "
      f"Tumblr: {'connected' if tumblr.authenticated else 'not connected'}")


# ── Template globals ──────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    """Make is_admin and tumblr_auth available in every template."""
    return {
        'is_admin':    bool(session.get('logged_in')),
        'tumblr_auth': tumblr.authenticated,
        'blog_name':   TUMBLR_BLOG_NAME,
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
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            # Return JSON 401 for API/AJAX calls so the client can handle it
            # gracefully instead of silently following a redirect to login HTML.
            if (request.content_type or '').startswith('application/json') or \
               request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from flask import jsonify
                return jsonify({'error': 'Session expired — please reload the page'}), 401
            return redirect(url_for('login'))
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

    author_link_url = submitter_link
    if not author_link_url and submitter_tumblr:
        author_link_url = f'https://www.tumblr.com/{submitter_tumblr}'

    poem = save_poem_db(
        lines               = lines,
        title               = poem_title,
        author_user_id      = None,           # anonymous; logged-in flow lands later
        author_display_name = submitter_name,
        author_link_url     = author_link_url,
        status              = 'submitted',
    )
    create_poem_submission(poem['id'])

    return jsonify({
        'ok':         True,
        'message':    'Poem submitted for review!',
        'short_code': poem['short_code'],
    })


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
    # Admin uses server-persisted stable; public starts from empty (loads
    # from localStorage on the client side).
    stable = load_stable() if is_admin else []
    return render_template('poetry.html',
        stable_json=json.dumps(stable),
        optional_tags_json=json.dumps(OPTIONAL_TAGS),
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
    Public permalink for a poem. Phase 0.3 stub — full pasture/plain renderer
    arrives in Phase 1.5. For now we just confirm the poem exists and dump
    a minimal preview so we can verify the SQLite write path works.
    """
    poem = get_poem_by_short_code(short_code)
    if not poem:
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error=f'No poem found with code "{short_code}"',
        ), 404
    return render_template('poem_stub.html', poem=poem)


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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=False)
