"""
config.py - Central configuration for Horse Counter
All env vars and constants live here. Never import from app.py.
"""

import os
import hashlib
import secrets

# ── Tumblr OAuth ──────────────────────────────────────────────────────────────
TUMBLR_CONSUMER_KEY    = os.environ.get('TUMBLR_CONSUMER_KEY', '')
TUMBLR_CONSUMER_SECRET = os.environ.get('TUMBLR_CONSUMER_SECRET', '')
TUMBLR_REDIRECT_URI    = os.environ.get(
    'TUMBLR_REDIRECT_URI',
    'https://horsecounterbot.pythonanywhere.com/callback'
)
TUMBLR_BLOG_NAME       = os.environ.get('TUMBLR_BLOG_NAME', 'counting-horses')

# ── App security ──────────────────────────────────────────────────────────────
# SECRET_KEY: used for Flask session signing.
# On PythonAnywhere set this as a stable env var so sessions survive restarts.
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# PINS: comma-separated SHA-256 hashes of allowed PINs.
# To add a PIN, compute sha256(pin_string).hexdigest() and append to the env var.
# Example env value: "abc123hash,def456hash"
# Helper: python3 -c "import hashlib; print(hashlib.sha256(b'mypin').hexdigest())"
_raw_pins = os.environ.get('APP_PINS', '').strip().strip('"\'')
VALID_PIN_HASHES = {p.strip().strip('"\'') for p in _raw_pins.split(',') if p.strip()}


def check_pin(pin: str) -> bool:
    """Return True if the given PIN matches any stored hash."""
    if not pin:
        return False
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    return pin_hash in VALID_PIN_HASHES


# ── File paths ────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE     = os.path.join(BASE_DIR, 'tumblr_tokens.json')
DRAFTS_FILE    = os.path.join(BASE_DIR, 'drafts.json')
SUBMISSIONS_FILE = os.path.join(BASE_DIR, 'submissions.json')

# Dictionary: try new rich format first, fall back to legacy compressed format
HORSES_RICH_FILE      = os.path.join(BASE_DIR, 'data', 'horses.json.gz')
HORSES_LEGACY_FILE    = os.path.join(BASE_DIR, 'horses_compressed.json.gz')
HORSE_OVERRIDES_FILE  = os.path.join(BASE_DIR, 'data', 'horse_overrides.json')
FAMOUS_HORSES_FILE    = os.path.join(BASE_DIR, 'data', 'famous_horses.json')

# ── Session ───────────────────────────────────────────────────────────────────
SESSION_LIFETIME_SECONDS = 86400  # 24 hours

# ── Draft cache ───────────────────────────────────────────────────────────────
DRAFT_TTL_SECONDS = 3600  # drafts expire after 1 hour

# ── Post templates ────────────────────────────────────────────────────────────
POST_PREFIX_SINGLE = "<p><b>This post contains {count} horse{plural} ({density}% of the post)</b></p>"
POST_PREFIX_MULTI  = "<p><b>These posts contain {count} horse{plural} ({density}% of the post)</b></p>"
POST_SUFFIX = (
    "<p><small>Posts are selected by humans, processed automatically and queued "
    "to post. Click the link for more information about each horse. You can send "
    "a link or text to be counted to my ask box.</small></p>"
)


def format_prefix(count: int, is_multi: bool, density: float = 0.0) -> str:
    plural = 's' if count != 1 else ''
    template = POST_PREFIX_MULTI if is_multi else POST_PREFIX_SINGLE
    return template.format(count=count, plural=plural, density=density)


# ── Tags ──────────────────────────────────────────────────────────────────────
DEFAULT_TAGS = [
    "how many horses?",
    "{count} horse{plural}",
    "{density}% horse",
    "gimmick account",
    "counting-horses",
    "horseblr",
]

OPTIONAL_TAGS = [
    "request",
    "long post",
    "text post",
    "meme",
    "heritage post",
    "humor",
    "reply",
    "horse mention",
    "horse image",
    "image",
    "video",
    "animated gif",
    "art",
    "laugh rule",
    "informative",
    "vocabulary altering post",
    "lyrics",
    "poetry",
    "nsfw",
]

HORSE_EMOJIS = ["🐴", "🐎", "🏇", "🎠", "𓃗", "♞", "🥕", "🍎", "🦄"]


def get_horse_emoji(username: str) -> str:
    """Stable emoji for a username based on hash (not Python's randomised hash)."""
    if not username or username == 'unknown':
        return '🐴'
    # Use hashlib so result is stable across process restarts
    h = int(hashlib.md5(username.encode()).hexdigest(), 16)
    return HORSE_EMOJIS[h % len(HORSE_EMOJIS)]


def build_default_tags(count: int, density: float = 0.0) -> list[str]:
    plural = 's' if count != 1 else ''
    tags = []
    for t in DEFAULT_TAGS:
        t = t.replace('{count}', str(count))
        t = t.replace('{plural}', plural)
        t = t.replace('{density}', str(density))
        tags.append(t)
    return tags