"""
auth.py - Tumblr OAuth2 PKCE authentication

Handles token storage, refresh, and API requests.
Tokens are persisted to TOKEN_FILE (JSON on disk) so they survive
PythonAnywhere worker restarts.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from typing import Optional, Tuple

import requests
from flask import session

from config import (
    TUMBLR_CONSUMER_KEY,
    TUMBLR_CONSUMER_SECRET,
    TUMBLR_REDIRECT_URI,
    TOKEN_FILE,
)


class TumblrManager:

    def __init__(self):
        self.access_token:      Optional[str] = None
        self.refresh_token:     Optional[str] = None
        self.token_expires_at:  float         = 0
        self.authenticated:     bool          = False
        self._load_tokens()

    # ── Token persistence ─────────────────────────────────────────────────────

    def _load_tokens(self):
        try:
            if not os.path.exists(TOKEN_FILE):
                return
            with open(TOKEN_FILE) as f:
                tokens = json.load(f)
            self.access_token     = tokens.get('access_token', '')
            self.refresh_token    = tokens.get('refresh_token', '')
            self.token_expires_at = tokens.get('expires_at', 0)

            if time.time() > self.token_expires_at:
                self._refresh()
            elif self.access_token:
                self._test_auth()
        except Exception as e:
            print(f"Token load error: {e}")

    def _save_tokens(
        self,
        access_token:  str,
        refresh_token: Optional[str] = None,
        expires_in:    int           = 3600,
    ):
        try:
            expires_at = time.time() + expires_in
            tokens = {
                'access_token':  access_token,
                'refresh_token': refresh_token or self.refresh_token,
                'expires_at':    expires_at,
            }
            with open(TOKEN_FILE, 'w') as f:
                json.dump(tokens, f)

            self.access_token     = access_token
            if refresh_token:
                self.refresh_token = refresh_token
            self.token_expires_at = expires_at
            self._test_auth()
        except Exception as e:
            print(f"Token save error: {e}")

    # ── Token refresh ─────────────────────────────────────────────────────────

    def _refresh(self) -> bool:
        if not self.refresh_token:
            self.authenticated = False
            return False
        try:
            r = requests.post(
                'https://api.tumblr.com/v2/oauth2/token',
                data={
                    'grant_type':    'refresh_token',
                    'refresh_token': self.refresh_token,
                    'client_id':     TUMBLR_CONSUMER_KEY,
                    'client_secret': TUMBLR_CONSUMER_SECRET,
                },
                timeout=10,
            )
            if r.status_code == 200:
                d = r.json()
                self._save_tokens(
                    d.get('access_token'),
                    d.get('refresh_token'),
                    d.get('expires_in', 3600),
                )
                return True
        except Exception as e:
            print(f"Token refresh error: {e}")
        self.authenticated = False
        return False

    def _test_auth(self) -> bool:
        try:
            r = requests.get(
                'https://api.tumblr.com/v2/user/info',
                headers={'Authorization': f'Bearer {self.access_token}'},
                timeout=10,
            )
            if r.status_code == 401:
                if self._refresh():
                    return self._test_auth()
                self.authenticated = False
                return False
            self.authenticated = (r.status_code == 200)
            return self.authenticated
        except Exception:
            self.authenticated = False
            return False

    # ── API request ───────────────────────────────────────────────────────────

    def make_request(
        self,
        endpoint: str,
        method:   str  = 'GET',
        data:     dict = None,
    ) -> Optional[dict]:
        if not self.authenticated:
            return None

        # Proactively refresh if token expires within 5 minutes
        if time.time() > self.token_expires_at - 300:
            self._refresh()

        try:
            headers = {'Authorization': f'Bearer {self.access_token}'}
            url = f'https://api.tumblr.com/v2/{endpoint}'

            if method == 'GET':
                r = requests.get(url, headers=headers, params=data, timeout=10)
            else:
                r = requests.post(url, headers=headers, json=data, timeout=10)

            if r.status_code == 401:
                if self._refresh():
                    return self.make_request(endpoint, method, data)
                return None

            if r.status_code in (200, 201):
                return r.json()

            print(f"API {method} {endpoint} returned {r.status_code}: {r.text[:200]}")
            return None

        except Exception as e:
            print(f"API request error: {e}")
            return None

    # ── OAuth2 PKCE flow ──────────────────────────────────────────────────────

    def get_auth_url(self) -> Optional[str]:
        try:
            code_verifier = (
                base64.urlsafe_b64encode(secrets.token_bytes(32))
                .decode()
                .rstrip('=')
            )
            code_challenge = (
                base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                )
                .decode()
                .rstrip('=')
            )
            state = secrets.token_urlsafe(16)

            session['code_verifier'] = code_verifier
            session['oauth_state']   = state

            import urllib.parse
            params = {
                'client_id':             TUMBLR_CONSUMER_KEY,
                'response_type':         'code',
                'scope':                 'basic write offline_access',
                'redirect_uri':          TUMBLR_REDIRECT_URI,
                'state':                 state,
                'code_challenge':        code_challenge,
                'code_challenge_method': 'S256',
            }
            return 'https://www.tumblr.com/oauth2/authorize?' + urllib.parse.urlencode(params)
        except Exception as e:
            print(f"get_auth_url error: {e}")
            return None

    def exchange_code(
        self, code: str, code_verifier: str
    ) -> Tuple[Optional[str], Optional[str], int]:
        try:
            r = requests.post(
                'https://api.tumblr.com/v2/oauth2/token',
                data={
                    'grant_type':    'authorization_code',
                    'code':          code,
                    'redirect_uri':  TUMBLR_REDIRECT_URI,
                    'code_verifier': code_verifier,
                    'client_id':     TUMBLR_CONSUMER_KEY,
                    'client_secret': TUMBLR_CONSUMER_SECRET,
                },
                timeout=10,
            )
            if r.status_code == 200:
                d = r.json()
                return (
                    d.get('access_token'),
                    d.get('refresh_token'),
                    d.get('expires_in', 3600),
                )
        except Exception as e:
            print(f"exchange_code error: {e}")
        return None, None, 0

    def complete_auth(self, code: str, code_verifier: str) -> bool:
        access, refresh, expires_in = self.exchange_code(code, code_verifier)
        if access:
            self._save_tokens(access, refresh, expires_in)
            return self.authenticated
        return False
