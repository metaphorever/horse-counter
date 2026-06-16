"""
bluesky.py — Bluesky (AT Protocol) connector for cross-posting poems.

App-password auth (not OAuth). Set BLUESKY_HANDLE + BLUESKY_APP_PASSWORD in the
environment; the app password is a Bluesky "App Password" (Settings → App
Passwords), never the account's main password, and lives only in the VPS env.

Funnel-to-site: each post is a short text hook plus an external link card
pointing at the poem's poet.horse permalink.
"""

import time
from typing import Optional, Tuple

from config import BLUESKY_HANDLE, BLUESKY_APP_PASSWORD

# Re-login if the cached session is older than this (seconds).
_SESSION_TTL = 3600


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
        text: str,
        link_url: str,
        link_title: str,
        link_desc: str = '',
    ) -> Tuple[bool, Optional[str]]:
        """Post `text` plus an external link card. Returns (success, error)."""
        if not self.authenticated:
            return False, 'Bluesky not configured (BLUESKY_HANDLE / BLUESKY_APP_PASSWORD)'
        try:
            from atproto import models
            client = self._client_session()
            embed = models.AppBskyEmbedExternal.Main(
                external=models.AppBskyEmbedExternal.External(
                    uri=link_url,
                    title=link_title or 'A poem on poet.horse',
                    description=link_desc or '',
                )
            )
            client.send_post(text=text, embed=embed)
            return True, None
        except Exception as e:
            # Drop the cached session so the next attempt re-logs in cleanly.
            self._client = None
            return False, str(e)
