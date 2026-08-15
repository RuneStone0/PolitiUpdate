"""Persist small notify state (e.g. last known follower count) to a private
GitHub Gist, instead of local disk.

This is what lets notify-weekly run entirely on GitHub Actions with no local
volume — the shared SQLite DB and bot's /health endpoint (what notify-daily
needs) only exist on the UmbrelOS host, but the weekly follower check only
needs the X API, this gist, and the Prowl webhook.

Deliberately a separate gist from src.x_stats.gist's x-stats.json: that one
is public (the site fetches it anonymously); this one is internal state and
stays secret.
"""

import json
import os

import requests

GITHUB_API = "https://api.github.com/gists"

GIST_FILENAME = os.getenv("NOTIFY_STATE_GIST_FILENAME", "notify-state.json")
GIST_DESCRIPTION = os.getenv(
    "NOTIFY_STATE_GIST_DESCRIPTION",
    "PolitiUpdate notify internal state (not for public consumption).",
)
GIST_ID = os.getenv("NOTIFY_STATE_GIST_ID", "").strip()


def _token() -> str:
    token = os.getenv("GITHUB_GIST_TOKEN", "")
    if not token:
        raise RuntimeError(
            "GITHUB_GIST_TOKEN is not set. Required to persist notify state to a gist."
        )
    return token


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _find_gist_id(token: str) -> str | None:
    try:
        resp = requests.get(
            GITHUB_API, headers=_headers(token), params={"per_page": 100}, timeout=30
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None
    for gist in resp.json():
        if gist.get("description") == GIST_DESCRIPTION:
            return gist["id"]
    return None


def read() -> dict | None:
    """Return the last-persisted state dict, or None if there isn't one yet
    (first run, or the gist/token isn't reachable)."""
    token = _token()
    gist_id = GIST_ID or _find_gist_id(token)
    if not gist_id:
        return None
    try:
        resp = requests.get(f"{GITHUB_API}/{gist_id}", headers=_headers(token), timeout=30)
        resp.raise_for_status()
        content = resp.json()["files"][GIST_FILENAME]["content"]
        return json.loads(content)
    except (requests.RequestException, KeyError, json.JSONDecodeError):
        return None


def write(state: dict) -> None:
    """Create or update the gist holding the current state (secret gist)."""
    token = _token()
    body = {
        "description": GIST_DESCRIPTION,
        "public": False,
        "files": {GIST_FILENAME: {"content": json.dumps(state, indent=2)}},
    }
    gist_id = GIST_ID or _find_gist_id(token)
    if gist_id:
        resp = requests.patch(f"{GITHUB_API}/{gist_id}", headers=_headers(token), json=body, timeout=30)
    else:
        resp = requests.post(GITHUB_API, headers=_headers(token), json=body, timeout=30)
    resp.raise_for_status()
