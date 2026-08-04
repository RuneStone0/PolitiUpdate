"""Post to X via the API v2 endpoint using tweepy (OAuth 2.0)."""

import json
import logging
import os
import time
from pathlib import Path

import tweepy

from .config import (
    X_CLIENT_ID,
    X_CLIENT_SECRET,
    X_REDIRECT_URI,
    X_REFRESH_TOKEN,
    X_TOKEN_FILE,
    RATE_LIMIT_BACKOFF,
    DRY_RUN,
)

logger = logging.getLogger(__name__)

SCOPES = ["tweet.read", "tweet.write", "users.read", "offline.access"]


def _load_tokens() -> dict:
    if not os.path.exists(X_TOKEN_FILE):
        raise RuntimeError(
            f"X token file not found at {X_TOKEN_FILE}. "
            "Run 'python -m src.bot.auth' first to authorize."
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
    new_tokens = oauth2.refresh_token(
        "https://api.x.com/2/oauth2/token",
        refresh_token=refresh_token,
    )
    new_tokens["obtained_at"] = int(time.time())
    return new_tokens


def _get_client() -> tweepy.Client:
    """Create an authenticated tweepy Client for API v2 (OAuth 2.0 Bearer)."""
    if not all([X_CLIENT_ID, X_CLIENT_SECRET]):
        raise RuntimeError(
            "X OAuth 2.0 credentials not configured. "
            "Set X_CLIENT_ID and X_CLIENT_SECRET."
        )

    tokens = _get_tokens()
    now = int(time.time())
    expires_at = tokens.get("obtained_at", 0) + tokens.get("expires_in", 7200)

    if now > expires_at - 60:
        logger.info("Access token expired, refreshing...")
        tokens = _refresh_access_token(tokens["refresh_token"])
        _save_tokens(tokens)

    return tweepy.Client(bearer_token=tokens["access_token"])


def _get_tokens() -> dict:
    """Get tokens from env var or file. On first run with X_REFRESH_TOKEN,
    performs an initial refresh and persists to the token file."""
    if X_REFRESH_TOKEN:
        logger.info("Using X_REFRESH_TOKEN from environment (initial refresh)...")
        tokens = _refresh_access_token(X_REFRESH_TOKEN)
        _save_tokens(tokens)
        return tokens
    return _load_tokens()


def post_tweet(text: str, reply_to: str | None = None) -> str | None:
    """Post a tweet and return its ID, or None on failure.

    Handles X rate limits by sleeping and retrying once.
    In dry-run mode, logs the post without sending it.

    Args:
        text: The tweet text.
        reply_to: If set, post as a reply to this tweet ID.
    """
    if DRY_RUN:
        label = f"REPLY to {reply_to}" if reply_to else "MAIN"
        logger.info("DRY-RUN would post %s (%d chars): %s", label, len(text), text[:200])
        return "dry-run"

    client = _get_client()

    kwargs = {"text": text}
    if reply_to:
        kwargs["in_reply_to_tweet_id"] = reply_to

    try:
        response = client.create_tweet(**kwargs)
        tweet_id = response.data["id"]
        label = f"reply to {reply_to}" if reply_to else ""
        logger.info("Posted tweet %s %s (%d chars)", tweet_id, label, len(text))
        return str(tweet_id)

    except tweepy.TooManyRequests as e:
        logger.warning(
            "Rate limited by X. Backing off for %d seconds.",
            RATE_LIMIT_BACKOFF,
        )
        time.sleep(RATE_LIMIT_BACKOFF)
        try:
            response = client.create_tweet(**kwargs)
            tweet_id = response.data["id"]
            logger.info("Posted tweet %s after backoff (%d chars)", tweet_id, len(text))
            return str(tweet_id)
        except Exception as e2:
            logger.error("Failed to post after backoff: %s", e2)
            return None

    except tweepy.Forbidden as e:
        logger.error("X API forbidden (check app permissions): %s", e)
        return None

    except tweepy.TweepyException as e:
        logger.error("X API error: %s", e)
        return None


def post_thread(texts: list[str]) -> list[str | None]:
    """Post a thread of tweets.

    First tweet is the main post; each subsequent tweet is a reply
    to the previous one (reversed: latest is main, older are replies).

    Returns list of tweet IDs (or None for failed posts).
    """
    if not texts:
        return []

    ids: list[str | None] = []
    reply_to: str | None = None

    for i, text in enumerate(texts):
        tweet_id = post_tweet(text, reply_to=reply_to)
        ids.append(tweet_id)
        if tweet_id and tweet_id != "dry-run":
            reply_to = tweet_id
        elif tweet_id == "dry-run":
            reply_to = "dry-run"

    return ids
