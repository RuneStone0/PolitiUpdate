"""Authenticated X API v2 client for the followers app.

Mirrors src/bot/poster.py's auth strategy (OAuth 1.0a first, OAuth 2.0
user-context fallback) but kept independent per the pattern in
src/x_stats/main.py — each standalone app owns its own auth.
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

# follows.read/follows.write are required for OAuth 2.0 user-context follow
# calls. Tokens minted by `python -m src.bot.auth` (which only requests
# tweet.read/tweet.write/users.read/offline.access) will 403 on follow
# endpoints — prefer OAuth 1.0a, or re-authorize with these scopes.
SCOPES = ["tweet.read", "users.read", "follows.read", "follows.write", "offline.access"]


def _load_tokens() -> dict:
    if not os.path.exists(X_TOKEN_FILE):
        raise RuntimeError(
            f"X token file not found at {X_TOKEN_FILE}. "
            "Run 'python -m src.bot.auth' first to authorize (with follows.read/"
            "follows.write scopes), or configure OAuth 1.0a credentials instead."
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
    """Return an authenticated tweepy Client and its auth type ("oauth1"/"oauth2")."""
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

    if not all([X_CLIENT_ID, X_CLIENT_SECRET]):
        raise RuntimeError(
            "X API credentials not configured. "
            "Set OAuth 1.0a credentials (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET) "
            "or OAuth 2.0 credentials (X_CLIENT_ID, X_CLIENT_SECRET)."
        )

    tokens = _get_tokens()
    now = int(time.time())
    expires_at = tokens.get("obtained_at", 0) + tokens.get("expires_in", 7200)
    if now > expires_at - 60:
        tokens = _refresh_access_token(tokens["refresh_token"])
        _save_tokens(tokens)

    return tweepy.Client(bearer_token=tokens["access_token"]), "oauth2"
