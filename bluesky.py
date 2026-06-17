"""
bluesky.py — Bluesky (AT Protocol) connector for cross-posting poems.

App-password auth (not OAuth). Set BLUESKY_HANDLE + BLUESKY_APP_PASSWORD in the
environment; the app password is a Bluesky "App Password" (Settings → App
Passwords), never the account's main password, and lives only in the VPS env.

Funnel-to-site: each post is a byline hook + as much of the poem as fits the
300-char limit (whole-horse truncation) + reach hashtags (as tappable facets),
plus an external link card to the poem's poet.horse permalink. Adult poems carry
a self-label. The permalink lives in the card only — it costs no text budget.
"""

import time
from typing import List, Optional, Tuple

from config import BLUESKY_HANDLE, BLUESKY_APP_PASSWORD

# Re-login if the cached session is older than this (seconds).
_SESSION_TTL = 3600

# Bluesky's hard limit is 300 graphemes. We budget to 290 and count codepoints
# (len) — identical for Latin horse names, and the 10-char margin absorbs the
# grapheme gap for anything unusual rather than pulling in a grapheme dep. 2.3.
_TEXT_BUDGET = 290
_TRUNC = '[…]'        # "[…]" truncation marker
_HEADER_SEP = '\n\n'       # blank line between header and poem sample
_TAG_SEP = '\n\n'          # blank line between poem and the hashtag line


def _compose_body(header: str, line_horses: List[List[str]], tag_render: str) -> str:
    """Header + as much of the poem as fits the budget, whole horses only.

    Lines are kept whole; if the poem overflows, append a […] marker. If even
    the first line won't fit whole, cut it at a horse boundary (the last shown
    line ends the poem partway). `tag_render` is the rendered hashtag line whose
    length must be reserved here so the connector can append it within budget.
    """
    tag_block = (_TAG_SEP + tag_render) if tag_render else ''
    remaining = _TEXT_BUDGET - len(header) - len(_HEADER_SEP) - len(tag_block)

    lines = [' '.join(h for h in horses if h) for horses in line_horses if any(horses)]
    if not lines or remaining <= 0:
        return header  # nothing fits; header + card carry the post

    def fit(budget: int):
        out, used = [], 0
        for ln in lines:
            add = len(ln) + (1 if out else 0)   # +1 for the joining '\n'
            if used + add <= budget:
                out.append(ln)
                used += add
            else:
                return out, True
        return out, False

    fitted, truncated = fit(remaining)
    if truncated:
        fitted, _ = fit(remaining - len('\n' + _TRUNC))

    if not fitted:
        # Degenerate: first line too long alone — cut it at a horse boundary.
        budget_d = remaining - len('\n' + _TRUNC)
        parts, used = [], 0
        for disp in line_horses[0]:
            add = len(disp) + (1 if parts else 0)
            if used + add <= budget_d:
                parts.append(disp)
                used += add
            else:
                break
        fitted = [' '.join(parts)] if parts else []
        truncated = True

    body = header + _HEADER_SEP + '\n'.join(fitted)
    if truncated:
        body += '\n' + _TRUNC
    return body


class BlueskyManager:
    """Mirrors TumblrManager's shape (an `authenticated` flag + a post method).

    Login is lazy: we only talk to Bluesky on the first dispatch, so a missing
    `atproto` install or bad creds can't break app startup. `authenticated`
    reports whether both creds are configured; a genuine login failure surfaces
    as the error string from `post_poem`.
    """

    def __init__(self):
        self._client = None
        self._logged_in_at = 0.0
        self.authenticated = bool(BLUESKY_HANDLE and BLUESKY_APP_PASSWORD)

    def _client_session(self):
        """Return a logged-in atproto Client, re-using the session within TTL."""
        if self._client is not None and (time.time() - self._logged_in_at) < _SESSION_TTL:
            return self._client
        from atproto import Client  # lazy import keeps the dep optional at boot
        client = Client()
        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
        self._client = client
        self._logged_in_at = time.time()
        return client

    def post_poem(
        self,
        header: str,
        line_horses: List[List[str]],
        tags: List[str],
        link_url: str,
        link_title: str,
        link_desc: str = '',
        self_label: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Post a poem sample + hashtags + external link card. Returns (ok, err).

        `header` is the byline hook, `line_horses` the poem as per-line horse
        displays (sampled here to fit Bluesky's limit), `tags` the reach hashtags
        (rendered as tappable facets), `self_label` an optional moderation label
        (e.g. 'sexual'). The permalink lives in the card only.
        """
        if not self.authenticated:
            return False, 'Bluesky not configured (BLUESKY_HANDLE / BLUESKY_APP_PASSWORD)'
        try:
            from atproto import client_utils, models
            client = self._client_session()

            tag_render = ' '.join('#' + t for t in tags)
            body = _compose_body(header, line_horses, tag_render)

            builder = client_utils.TextBuilder()
            builder.text(body)
            if tags:
                builder.text(_TAG_SEP)
                for i, tag in enumerate(tags):
                    if i:
                        builder.text(' ')
                    builder.tag('#' + tag, tag)

            embed = models.AppBskyEmbedExternal.Main(
                external=models.AppBskyEmbedExternal.External(
                    uri=link_url,
                    title=link_title or 'A poem on poet.horse',
                    description=link_desc or '',
                )
            )
            labels = None
            if self_label:
                labels = models.ComAtprotoLabelDefs.SelfLabels(
                    values=[models.ComAtprotoLabelDefs.SelfLabel(val=self_label)]
                )
            record = models.AppBskyFeedPost.Record(
                created_at=client.get_current_time_iso(),
                text=builder.build_text(),
                facets=builder.build_facets(),
                embed=embed,
                langs=['en'],
                labels=labels,
            )
            client.app.bsky.feed.post.create(client.me.did, record)
            return True, None
        except Exception as e:
            # Drop the cached session so the next attempt re-logs in cleanly.
            self._client = None
            return False, str(e)
