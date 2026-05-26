"""
github_issues.py — GitHub issue creation for poet.horse bug reports.

Requires GITHUB_TOKEN env var (personal access token with repo scope).
GITHUB_REPO can be overridden via env; defaults to the primary repo.
"""

import os

import requests as _req

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO  = os.environ.get('GITHUB_REPO', 'metaphorever/horse-counter')


def create_issue(title: str, body: str, labels: list | None = None) -> str | None:
    """
    Open a GitHub issue. Returns the issue HTML URL on success, None on failure.
    Failure is non-fatal — callers should continue regardless.
    """
    if not GITHUB_TOKEN:
        return None
    try:
        resp = _req.post(
            f'https://api.github.com/repos/{GITHUB_REPO}/issues',
            headers={
                'Authorization':        f'Bearer {GITHUB_TOKEN}',
                'Accept':               'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            },
            json={
                'title':  title[:256],
                'body':   body,
                'labels': labels or [],
            },
            timeout=10,
        )
        if resp.status_code == 201:
            return resp.json().get('html_url')
        print(f'GitHub issue creation failed: {resp.status_code} {resp.text[:200]}')
    except Exception as e:
        print(f'GitHub issue creation error: {e}')
    return None
