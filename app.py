"""
app.py - Flask routes for Horse Counter

Public routes (no login required):
  GET  /               main input page (URL + text tabs)
  POST /               process URL or text, show count + submit option
  POST /submit         save a counted post as a public submission
  POST /submit/poem    save a public poem submission
  GET  /poetry         poetry editor
  POST /poetry/search  horse name search

Admin routes (login required):
  POST /               reply mode
  POST /queue          post/queue/draft a reviewed post
  GET  /auth           start Tumblr OAuth
  GET  /callback       OAuth callback
  GET  /submissions    review pending public submissions
  POST /submissions/approve  move a submission to the review page
  POST /submissions/reject   discard a submission
  POST /poetry/pasture/*     server-persisted pasture (admin only)
  POST /poetry/post          post a poem directly (admin only)
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
    OPTIONAL_TAGS, POST_SUFFIX, format_prefix,
)
from auth import TumblrManager
from matcher import (
    HorseDictionary, ChainCounter,
    find_horses_in_text, render_chain_item, compute_stats,
)
from post_builder import extract_post
from famous import FamousHorses
from poetry import (
    search_dictionary, load_pasture, add_to_pasture,
    remove_from_pasture, clear_pasture,
    build_poem_html, compute_poem_stats, format_poem_prefix,
    POEM_SUFFIX, build_poem_tags, order_poem_tags, order_request_tags,
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

def _attribution_html(name: str, tumblr: str, prefix: str = 'Submitted by') -> str:
    """Build an attribution line for the post body, or empty string if no credit given."""
    if not name and not tumblr:
        return ''
    if tumblr:
        display = name or f'@{tumblr}'
        return f'<p>{prefix} <a href="https://www.tumblr.com/{tumblr}">{display}</a></p>'
    return f'<p>{prefix} {name}</p>'


def _poem_attr_html(title: str, name: str, tumblr: str) -> str:
    """Build '<em>Title</em> by Author' attribution for the poem prefix, or empty string."""
    title_part = f'<em>{title}</em>' if title else ''
    if name or tumblr:
        display = name or f'@{tumblr}'
        author_part = f'<a href="https://www.tumblr.com/{tumblr}">{display}</a>' if tumblr else display
        if title_part:
            return f'<p>{title_part} by {author_part}</p>'
        return f'<p>by {author_part}</p>'
    return f'<p>{title_part}</p>' if title_part else ''


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

    # ── Admin + Tumblr + horses → direct review/post flow ──
    if is_admin and tumblr.authenticated and horse_count > 0:
        usernames = set()
        for item in post_data.get('reply_chain', post_data['chain']):
            u = item.get('username', '')
            if u and u not in ('unknown', 'reply', ''):
                usernames.add(u)

        default_tags = build_default_tags(horse_count, stats['horse_density'])
        prefix       = format_prefix(horse_count, post_data.get('is_multi', False), stats['horse_density'])

        # Famous tags go first so they're visible at the top of the custom field
        username_tags = sorted(usernames)
        all_custom_tags = famous_tags + username_tags

        draft_id = save_draft({
            'post_data':    post_data,
            'horse_count':  horse_count,
            'linked_html':  linked_html,
            'stats':        stats,
            'is_text_post': post_data.get('is_text_post', False),
            'is_reply':     post_data.get('is_reply', False),
            'is_fallback':  post_data.get('is_fallback', False),
        })

        return render_template('review.html',
            draft_id=draft_id,
            horse_count=horse_count,
            stats=stats,
            content=linked_html,
            pre=prefix,
            mid='',
            suf=POST_SUFFIX,
            default_tags=default_tags,
            optional_tags=OPTIONAL_TAGS,
            custom_tags=','.join(all_custom_tags),
            auto_check_tags=_auto_check_tags(post_data),
            is_fallback=post_data.get('is_fallback', False),
            famous_found=famous_found,
            error=None,
        )

    # ── Public user with horses → save draft so they can submit it ──
    draft_id = None
    if not is_admin and horse_count > 0:
        draft_id = save_draft({
            'post_data':    post_data,
            'horse_count':  horse_count,
            'linked_html':  linked_html,
            'stats':        stats,
            'is_text_post': post_data.get('is_text_post', False),
            'is_reply':     False,
            'is_fallback':  post_data.get('is_fallback', False),
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

    tags = assemble_tags(
        default_tags=request.form.getlist('tag_default'),
        optional_tags=request.form.getlist('tag_optional'),
        custom_tags=request.form.get('tags_custom', ''),
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
    """Accept a counted post submission from a public user."""
    draft_id = request.form.get('draft_id', '')
    draft    = load_draft(draft_id)

    if not draft:
        return render_template('index.html',
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error='Submission timed out — please count again and try again',
        )

    sub_type         = 'text' if draft.get('is_text_post') else 'url'
    submitter_name   = _sanitize_name(request.form.get('submitter_name', ''))
    submitter_tumblr = _sanitize_tumblr(request.form.get('submitter_tumblr', ''))
    save_submission(sub_type, {
        'post_data':        draft.get('post_data', {}),
        'horse_count':      draft['horse_count'],
        'linked_html':      draft['linked_html'],
        'stats':            draft.get('stats', {}),
        'is_text_post':     draft.get('is_text_post', False),
        'is_fallback':      draft.get('is_fallback', False),
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
    """Accept a poem submission from a public user."""
    from flask import jsonify
    data   = request.get_json()
    lines  = data.get('lines', [])

    if not any(lines):
        return jsonify({'ok': False, 'error': 'Poem is empty'})

    flat             = [h for line in lines for h in line]
    horse_count      = len(flat)
    poem_html        = build_poem_html(lines)
    total_words      = sum(len(h['name'].split()) for h in flat)
    submitter_name   = _sanitize_name(data.get('submitter_name', ''))
    submitter_tumblr = _sanitize_tumblr(data.get('submitter_tumblr', ''))
    poem_title       = _sanitize_name(data.get('poem_title', ''))

    save_submission('poem', {
        'post_data':        {},
        'horse_count':      horse_count,
        'linked_html':      poem_html,
        'poem_title':       poem_title,
        'stats':            {
            'horse_density': 100.0,
            'total_words':   total_words,
            'linked_words':  total_words,
        },
        'is_text_post':     True,
        'is_fallback':      False,
        'submitter_name':   submitter_name,
        'submitter_tumblr': submitter_tumblr,
    })
    return jsonify({'ok': True, 'message': 'Poem submitted for review!'})


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

    is_poem   = sub.get('type') == 'poem'
    count_pre = format_prefix(horse_count, False, density)
    name_tag  = f'by {submitter_name}' if submitter_name else ''
    tumblr_tag = submitter_tumblr if submitter_tumblr else ''

    if is_poem:
        # Poem: "Title by Author" line goes above the count line in pre; mid is empty
        attr = _poem_attr_html(sub.get('poem_title', ''), submitter_name, submitter_tumblr)
        pre  = (attr + '\n' + count_pre) if attr else count_pre
        mid  = ''
        base_tags  = sub.get('poem_tags', '')
        extra_tags = order_request_tags(base_tags, name_tag, tumblr_tag)
    else:
        # URL/text: "Requested by Name" goes in mid; no poem tags
        pre  = count_pre
        mid  = _attribution_html(submitter_name, submitter_tumblr, prefix='Requested by')
        extra_tags = order_request_tags('', name_tag, tumblr_tag)

    return render_template('review.html',
        draft_id=draft_id,
        horse_count=horse_count,
        stats=stats,
        content=sub.get('linked_html', ''),
        pre=pre,
        mid=mid,
        suf=POST_SUFFIX,
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
    # Admin uses server-persisted pasture; public starts from empty (loads
    # from localStorage on the client side).
    pasture = load_pasture() if is_admin else []
    return render_template('poetry.html',
        pasture_json=json.dumps(pasture),
        optional_tags_json=json.dumps(OPTIONAL_TAGS),
    )


@app.route('/poetry/search', methods=['POST'])
def poetry_search():
    from flask import jsonify
    data    = request.get_json(silent=True) or {}
    query   = data.get('query', '')
    results = search_dictionary(query, dictionary)
    return jsonify(results)


@app.route('/poetry/pasture/add', methods=['POST'])
@login_required
def pasture_add():
    from flask import jsonify
    data   = request.get_json()
    horses = add_to_pasture(data['name'], data['display'], data['url'])
    return jsonify({'horses': horses})


@app.route('/poetry/pasture/remove', methods=['POST'])
@login_required
def pasture_remove():
    from flask import jsonify
    data   = request.get_json()
    horses = remove_from_pasture(data['name'])
    return jsonify({'horses': horses})


@app.route('/poetry/pasture/clear', methods=['POST'])
@login_required
def pasture_clear():
    from flask import jsonify
    clear_pasture()
    return jsonify({'ok': True})


@app.route('/poetry/post', methods=['POST'])
@login_required
def poetry_post():
    from flask import jsonify
    from queue_handler import _post_state, _create_text_post
    if not tumblr.authenticated:
        return jsonify({'ok': False, 'error': 'Not connected to Tumblr'})

    data   = request.get_json()
    lines  = data.get('lines', [])
    prefix = data.get('prefix', '')
    suffix = data.get('suffix', POEM_SUFFIX)
    tags   = data.get('tags', '')
    action = data.get('action', 'queue')

    if not any(lines):
        return jsonify({'ok': False, 'error': 'Poem is empty'})

    submitter_name   = _sanitize_name(data.get('submitter_name', ''))
    submitter_tumblr = _sanitize_tumblr(data.get('submitter_tumblr', ''))
    poem_title       = _sanitize_name(data.get('poem_title', ''))
    title_html       = f'<p><em>{poem_title}</em></p>' if poem_title else ''
    attribution      = _attribution_html(submitter_name, submitter_tumblr, prefix='by')

    poem_html = build_poem_html(lines)
    body      = prefix + poem_html + suffix + title_html + attribution

    tags = order_poem_tags(
        tags,
        f'by {submitter_name}' if submitter_name else '',
        submitter_tumblr,
    )

    state     = _post_state(action)

    success, err = _create_text_post(tumblr.make_request, body, tags, state)
    if success:
        label = {'post': 'published', 'queue': 'queued', 'draft': 'saved as draft'}.get(action, 'queued')
        return jsonify({'ok': True, 'message': f'Poem {label}!'})
    return jsonify({'ok': False, 'error': err})


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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=False)
