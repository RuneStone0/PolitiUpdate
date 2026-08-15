"""Authenticated X API v2 client for the followers app.

Unlike src/bot/poster.py (which prefers OAuth 1.0a), this app prefers
OAuth 2.0: X API v2's GET /2/users/:id/followers only accepts OAuth 2.0
(App-only or user-context) — OAuth 1.0a is rejected with a 401 regardless
of API access tier. OAuth 2.0 user-context also covers follow/unfollow, so
one token can drive the whole app. Falls back to OAuth 1.0a only for
follow/unfollow if no OAuth 2.0 credentials are configured — that path
can act on followers but can't discover them, so `sync()` requires OAuth 2.0.

Kept independent per the pattern in src/x_stats/main.py — each standalone
app owns its own auth.
"""

import json
import os
import time
from pathlib import Path

import tweepy

from .config import (
    X_API_KEY,
    X_API_SECRET,
    X_ACCESS_TOKEN,
    X_ACCESS_SECRET,
    X_CLIENT_ID,
    X_CLIENT_SECRET,
    X_REDIRECT_URI,
    X_REFRESH_TOKEN,
    X_TOKEN_FILE,
)

# follows.read is required to list followers; follows.write to follow/unfollow
# over OAuth 2.0. A token minted by the *unpatched* `python -m src.bot.auth`
# (tweet.read/tweet.write/users.read/offline.access only) lacks both and will
# 401/403 here — re-run it after these scopes were added to src/bot/auth.py.
SCOPES = ["tweet.read", "users.read", "follows.read", "follows.write", "offline.access"]


def _load_tokens() -> dict:
    if not os.path.exists(X_TOKEN_FILE):
        raise RuntimeError(
            f"X token file not found at {X_TOKEN_FILE}. "
            "Run 'python -m src.bot.auth' first to authorize (it requests "
            "follows.read/follows.write scopes, needed for this app)."
        )
    with open(X_TOKEN_FILE) as f:
        return json.load(f)


def _save_tokens(tokens: dict) -> None:
    Path(X_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(X_TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def _refresh_access_token(refresh_token: str) -> dict:
    oauth2 = tweepy.OAuth2UserHandler(
        client_id=X_CLIENT_ID,
        client_secret=X_CLIENT_SECRET,
        redirect_uri=X_REDIRECT_URI,
        scope=SCOPES,
    )
    tokens = oauth2.refresh_token(
        "https://api.x.com/2/oauth2/token",
        refresh_token=refresh_token,
    )
    tokens["obtained_at"] = int(time.time())
    return tokens


def _get_tokens() -> dict:
    if X_REFRESH_TOKEN:
        tokens = _refresh_access_token(X_REFRESH_TOKEN)
        _save_tokens(tokens)
        return tokens
    return _load_tokens()


def get_client() -> tuple[tweepy.Client, str]:
    """Return an authenticated tweepy Client and its auth type ("oauth2"/"oauth1").

    Prefers OAuth 2.0 (required for the followers-list read); falls back to
    OAuth 1.0a only if no OAuth 2.0 credentials are configured, in which case
    callers that need the followers list (i.e. `sync()`) will fail with a
    clear 401 from X rather than silently degrading.
    """
    if all([X_CLIENT_ID, X_CLIENT_SECRET]):
        tokens = _get_tokens()
        now = int(time.time())
        expires_at = tokens.get("obtained_at", 0) + tokens.get("expires_in", 7200)
        if now > expires_at - 60:
            tokens = _refresh_access_token(tokens["refresh_token"])
            _save_tokens(tokens)

        return tweepy.Client(bearer_token=tokens["access_token"]), "oauth2"

    if all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        return (
            tweepy.Client(
                consumer_key=X_API_KEY,
                consumer_secret=X_API_SECRET,
                access_token=X_ACCESS_TOKEN,
                access_token_secret=X_ACCESS_SECRET,
            ),
            "oauth1",
        )

    raise RuntimeError(
        "X API credentials not configured. "
        "Set OAuth 2.0 credentials (X_CLIENT_ID, X_CLIENT_SECRET, and a token from "
        "'python -m src.bot.auth' or X_REFRESH_TOKEN) — required to list followers — "
        "or OAuth 1.0a credentials (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET) "
        "for follow/unfollow-only use."
    )
