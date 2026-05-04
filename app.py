"""
app.py - Flask routes for Horse Counter

Routes:
  GET  /login          login form
  POST /login          PIN check
  GET  /logout         clear session
  GET  /               main input page
  POST /               process URL / text / reply
  POST /queue          post/queue/draft the reviewed post
  GET  /auth           start Tumblr OAuth
  GET  /callback       OAuth callback
  GET  /submissions    (stub) view pending submissions
  POST /submit         (stub) public submission endpoint
"""

import os
from flask import (
    Flask, request, redirect, session, url_for,
    render_template, flash
)
from functools import wraps

from config import (
    SECRET_KEY, SESSION_LIFETIME_SECONDS,
    TUMBLR_BLOG_NAME, HORSES_RICH_FILE, HORSES_LEGACY_FILE,
    check_pin, get_horse_emoji, build_default_tags,
    OPTIONAL_TAGS, POST_SUFFIX, format_prefix,
)
from auth import TumblrManager
from matcher import (
    HorseDictionary, ChainCounter,
    find_horses_in_text, render_chain_item, compute_stats,
)
from post_builder import extract_post
from poetry import (
    search_dictionary, load_pasture, add_to_pasture,
    remove_from_pasture, clear_pasture,
    build_poem_html, compute_poem_stats, format_poem_prefix,
    POEM_SUFFIX, build_poem_tags,
)
from queue_handler import (
    save_draft, load_draft, delete_draft,
    assemble_tags, build_post_body, submit_post,
)

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = SESSION_LIFETIME_SECONDS

# ── Initialise singletons ─────────────────────────────────────────────────────

print("Initialising Horse Counter...")
dictionary = HorseDictionary(HORSES_RICH_FILE, HORSES_LEGACY_FILE)
tumblr     = TumblrManager()
print(f"Ready. Dictionary: {dictionary.source}, "
      f"Tumblr: {'connected' if tumblr.authenticated else 'not connected'}")


# ── Auth guard ────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            # Return JSON 401 for API/AJAX calls so the client can handle it gracefully
            # instead of silently following a redirect to the login HTML page.
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
@login_required
def index():
    if request.method == 'GET':
        return render_template('index.html',
            tumblr_auth=tumblr.authenticated,
            blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
        )

    form_type  = request.form.get('type', 'url')
    form_data  = {
        'url':        request.form.get('url', ''),
        'text':       request.form.get('text', ''),
        'reply_url':  request.form.get('reply_url', ''),
        'reply_text': request.form.get('reply_text', ''),
    }
    active_tab = {'url': 'url', 'text': 'text', 'reply': 'reply'}.get(form_type, 'url')

    def error(msg):
        return render_template('index.html',
            tumblr_auth=tumblr.authenticated,
            blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded,
            active_tab=active_tab,
            form=form_data,
            error=msg,
        )

    try:
        # ── URL: fetch post and reblog with count ──────────────────────────────
        if form_type == 'url':
            url = form_data['url'].strip()
            if not url:
                return error("Enter a URL")

            post_data = extract_post(
                url,
                make_api_request=tumblr.make_request if tumblr.authenticated else None,
            )
            if not post_data:
                return error("Could not fetch post — check the URL or try again")

            return _process_chain(post_data, active_tab='url', form=form_data)

        # ── Text: standalone post from pasted text ────────────────────────────
        elif form_type == 'text':
            text = form_data['text'].strip()
            if not text:
                return error("Enter some text")

            # Wrap in a minimal post_data structure
            pseudo_post = {
                'blog_name':   '',
                'post_id':     '',
                'post_url':    '',
                'reblog_key':  '',
                'chain':       [{'username': '', 'text': text}],
                'is_multi':    False,
                'is_fallback': False,
                'is_text_post': True,
            }
            return _process_chain(pseudo_post, active_tab='text', form=form_data)

        # ── Reply: reblog a post but count horses in your own reply text ───────
        elif form_type == 'reply':
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

            # Override chain: only count horses in the reply text
            post_data = dict(post_data)
            post_data['reply_text'] = reply_text
            post_data['is_reply']   = True
            # Replace chain with just the reply text for matching purposes
            post_data['reply_chain'] = post_data['chain']  # keep original for reblog
            post_data['chain']       = [{'username': 'reply', 'text': reply_text}]

            return _process_chain(post_data, active_tab='reply', form=form_data)

    except Exception as e:
        import traceback; traceback.print_exc()
        return error(f"Unexpected error: {e}")


def _process_chain(post_data: dict, active_tab: str, form: dict):
    """
    Run matching on all chain items with a shared ChainCounter,
    then either show review page (if authenticated + horses found)
    or show simple count result.
    """
    chain  = post_data['chain']
    counter = ChainCounter(dictionary)

    # ── Find horses in every chain item ──
    chain_matches = []
    for item in chain:
        matches = find_horses_in_text(item['text'], dictionary)
        chain_matches.append(matches)

    total_horse_occurrences = sum(len(m) for m in chain_matches)

    # ── Render HTML for each chain item (consumes counter) ──
    rendered_parts = []
    total_linked_words = 0

    for item, matches in zip(chain, chain_matches):
        html, linked_words = render_chain_item(item['text'], matches, counter)
        total_linked_words += linked_words
        rendered_parts.append({
            'username': item['username'],
            'html':     html,
        })

    # ── Stats ──
    raw_texts = [item['text'] for item in chain]
    stats = compute_stats(raw_texts, counter)
    # Override linked_words with the accurate per-render count
    stats['linked_words'] = total_linked_words
    total_words = stats['total_words']
    stats['horse_density'] = (
        round(total_linked_words / total_words * 100, 1)
        if total_words > 0 else 0.0
    )

    horse_count = counter.total_linked()  # unique linked occurrences

    # ── Build combined HTML for review ──
    if post_data.get('is_multi') or len(rendered_parts) > 1:
        content_html_parts = []
        for i, part in enumerate(rendered_parts):
            if part['username']:
                emoji = get_horse_emoji(part['username'])
                content_html_parts.append(
                    f'<p class="chain-username">{emoji} @{part["username"]}</p>'
                )
            content_html_parts.append(part['html'])
            if i < len(rendered_parts) - 1:
                content_html_parts.append('<hr class="chain-sep">')
        linked_html = ''.join(content_html_parts)
    else:
        part = rendered_parts[0]
        if part['username']:
            emoji = get_horse_emoji(part['username'])
            linked_html = f'<p class="chain-username">{emoji} @{part["username"]}</p>{part["html"]}'
        else:
            linked_html = part['html']

    # ── If not authenticated or no horses, just show count ──
    if not tumblr.authenticated or horse_count == 0:
        all_matches = [m for matches in chain_matches for m in matches]
        return render_template('index.html',
            tumblr_auth=tumblr.authenticated,
            blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded,
            active_tab=active_tab,
            form=form,
            result={
                'count':  horse_count,
                'horses': all_matches,
                'stats':  stats,
            },
        )

    # ── Build usernames for custom tags ──
    usernames = set()
    # Use reply_chain for reply posts (original chain authors), not reply text username
    source_chain = post_data.get('reply_chain', post_data['chain'])
    for item in source_chain:
        u = item.get('username', '')
        if u and u not in ('unknown', 'reply', ''):
            usernames.add(u)

    default_tags = build_default_tags(horse_count, stats['horse_density'])
    prefix       = format_prefix(horse_count, post_data.get('is_multi', False), stats['horse_density'])

    # ── Save draft and go to review ──
    draft_id = save_draft({
        'post_data':    post_data,
        'horse_count':  horse_count,
        'linked_html':  linked_html,
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
        custom_tags=','.join(sorted(usernames)),
        is_fallback=post_data.get('is_fallback', False),
        error=None,
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
            tumblr_auth=tumblr.authenticated,
            blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            error='Draft expired — please re-process the post',
        )

    action  = request.form.get('action', 'queue')
    prefix  = request.form.get('pre', '')
    middle  = request.form.get('mid', '')
    suffix  = request.form.get('suf', POST_SUFFIX)

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
            tumblr_auth=tumblr.authenticated,
            blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded,
            active_tab='url',
            form={},
            queued=action_label,
        )

    # Failed — return to review with error
    return render_template('review.html',
        draft_id=draft_id,
        horse_count=draft['horse_count'],
        stats=None,
        content=draft['linked_html'],
        pre=prefix,
        mid=middle,
        suf=suffix,
        default_tags=request.form.getlist('tag_default'),
        optional_tags=OPTIONAL_TAGS,
        custom_tags=request.form.get('tags_custom', ''),
        is_fallback=draft.get('is_fallback', False),
        error=err_msg,
    )


# ── Tumblr OAuth ──────────────────────────────────────────────────────────────

@app.route('/auth')
@login_required
def auth():
    from config import TUMBLR_CONSUMER_KEY
    if not TUMBLR_CONSUMER_KEY:
        return render_template('index.html',
            tumblr_auth=False,
            blog_name=TUMBLR_BLOG_NAME,
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
        tumblr_auth=False,
        blog_name=TUMBLR_BLOG_NAME,
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
            tumblr_auth=False, blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded, active_tab='url', form={},
            error=f'Tumblr auth error: {error}',
        )

    if not code:
        return render_template('index.html',
            tumblr_auth=False, blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded, active_tab='url', form={},
            error='Auth failed: no code received',
        )

    if state != session.get('oauth_state'):
        return render_template('index.html',
            tumblr_auth=False, blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded, active_tab='url', form={},
            error='Auth failed: state mismatch (try again)',
        )

    code_verifier = session.pop('code_verifier', None)
    session.pop('oauth_state', None)

    if not code_verifier:
        return render_template('index.html',
            tumblr_auth=False, blog_name=TUMBLR_BLOG_NAME,
            horses_loaded=dictionary.loaded, active_tab='url', form={},
            error='Auth failed: missing code verifier (session may have expired)',
        )

    if tumblr.complete_auth(code, code_verifier):
        return redirect(url_for('index'))

    return render_template('index.html',
        tumblr_auth=False, blog_name=TUMBLR_BLOG_NAME,
        horses_loaded=dictionary.loaded, active_tab='url', form={},
        error='Auth failed: could not exchange code for token',
    )


# ── Submissions (stub) ────────────────────────────────────────────────────────

@app.route('/submissions')
@login_required
def submissions():
    """Placeholder — will show pending public submissions for review."""
    return render_template('index.html',
        tumblr_auth=tumblr.authenticated,
        blog_name=TUMBLR_BLOG_NAME,
        horses_loaded=dictionary.loaded,
        active_tab='url',
        form={},
        error='Submissions screen coming soon',
    )


@app.route('/submit', methods=['POST'])
def public_submit():
    """Stub public endpoint for future ask/submission intake."""
    return ('Submissions not yet open', 503)


# ── Poetry editor ────────────────────────────────────────────────────────────

@app.route('/poetry')
@login_required
def poetry_editor():
    import json
    pasture = load_pasture()
    return render_template('poetry.html',
        pasture_json=json.dumps(pasture),
        optional_tags_json=json.dumps(OPTIONAL_TAGS),
    )


@app.route('/poetry/search', methods=['POST'])
@login_required
def poetry_search():
    from flask import jsonify
    data       = request.get_json()
    query      = data.get('query', '')
    return_all = data.get('return_all', False)
    results    = search_dictionary(query, dictionary, return_all=return_all)
    return jsonify(results)


@app.route('/poetry/pasture/add', methods=['POST'])
@login_required
def pasture_add():
    from flask import jsonify
    data    = request.get_json()
    horses  = add_to_pasture(data['name'], data['display'], data['url'])
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

    poem_html = build_poem_html(lines)
    body      = prefix + poem_html + suffix
    state     = _post_state(action)

    success, err = _create_text_post(tumblr.make_request, body, tags, state)
    if success:
        label = {'post': 'published', 'queue': 'queued', 'draft': 'saved as draft'}.get(action, 'queued')
        return jsonify({'ok': True, 'message': f'Poem {label}!'})
    return jsonify({'ok': False, 'error': err})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=False)
