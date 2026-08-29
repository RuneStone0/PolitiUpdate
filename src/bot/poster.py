"""Post to X via the API v2 endpoint using tweepy."""

import json
import logging
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
    RATE_LIMIT_BACKOFF,
)

logger = logging.getLogger(__name__)

# Must match src/bot/auth.py's SCOPES exactly — oauthlib's refresh_token()
# compares this list against what the token actually carries and raises if
# they differ (even on an otherwise-successful refresh), so this needs to
# track whatever scopes the token was minted with, not just what this module
# itself needs.
SCOPES = ["tweet.read", "tweet.write", "users.read", "offline.access"]


def _raw_response_detail(e: tweepy.TweepyException) -> str:
    """Best-effort extraction of the raw response body from a tweepy
    exception. Tweepy's own message only surfaces `errors[]`/`detail`;
    the raw body may carry extra fields (e.g. a `type` doc link) that
    explain the failure more precisely."""
    response = getattr(e, "response", None)
    if response is None:
        return ""
    try:
        return response.text
    except Exception:
        return ""


def _get_client_oauth1() -> tweepy.Client:
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        raise RuntimeError(
            "X API OAuth 1.0a credentials not configured. "
            "Set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET."
        )
    return tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET,
    )


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


def _get_client() -> tuple[tweepy.Client, str]:
    """Create an authenticated tweepy Client. Tries OAuth 1.0a first (free tier),
    falls back to OAuth 2.0 Bearer token (Basic tier+)."""
    if all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        return _get_client_oauth1(), "oauth1"

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
        logger.info("Access token expired, refreshing...")
        tokens = _refresh_access_token(tokens["refresh_token"])
        _save_tokens(tokens)

    # Return client along with type so callers can select the correct auth mode
    return tweepy.Client(bearer_token=tokens["access_token"]), "oauth2"


def _get_tokens() -> dict:
    """Load the current token, preferring the persisted file over X_REFRESH_TOKEN.

    X rotates the refresh token on every use, so a static X_REFRESH_TOKEN env
    var is only good for bootstrapping the first run against a fresh/empty
    data volume — every refresh after that must use the persisted file (kept
    current by each refresh), or it tries to reuse an already-consumed
    refresh token and fails.
    """
    if os.path.exists(X_TOKEN_FILE):
        return _load_tokens()
    if X_REFRESH_TOKEN:
        logger.info("Using X_REFRESH_TOKEN from environment (initial refresh)...")
        tokens = _refresh_access_token(X_REFRESH_TOKEN)
        _save_tokens(tokens)
        return tokens
    return _load_tokens()


def post_tweet(text: str, reply_to: str | None = None) -> str | None:
    """Post a tweet and return its ID, or None on failure.

    Handles X rate limits by sleeping and retrying once.

    Args:
        text: The tweet text.
        reply_to: If set, post as a reply to this tweet ID.
    """
    try:
        result = _get_client()
    except RuntimeError:
        # Missing/incomplete credentials or a missing token file is a real
        # config problem, not transient X flakiness — let it propagate so
        # src/bot/main.py still pages on it.
        raise
    except Exception as e:
        # _get_client() also refreshes the OAuth 2.0 token when it's expired,
        # and a stale/consumed refresh token makes X answer that refresh with
        # 401 invalid_grant. oauthlib surfaces it as InvalidGrantError — a
        # plain Exception, NOT a tweepy.TweepyException — so the create_tweet
        # handlers below never see it, and it used to escape uncaught to
        # src/bot/main.py and page on every item. A dead token needs re-auth,
        # so alert once with a stable message (the Prowl handler dedups
        # identical messages); anything else (e.g. a network blip) is transient
        # noise.
        if getattr(e, "error", None) == "invalid_grant":
            logger.error(
                "X OAuth2 token refresh failed (invalid_grant): refresh token is "
                "stale or consumed — re-authorize with `python -m src.bot.auth`"
            )
        else:
            logger.warning("Could not obtain X client: %s", e)
        return None

    # Backwards-compat: _get_client may return either a client or (client, type)
    if isinstance(result, tuple):
        client, client_type = result
    else:
        client = result
        client_type = None

    kwargs = {"text": text}
    if reply_to:
        kwargs["in_reply_to_tweet_id"] = reply_to

    try:
        if client_type == "oauth2":
            response = client.create_tweet(user_auth=False, **kwargs)
        else:
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
            # Same known-flaky bucket as the generic TweepyException case
            # below — the retry loop (see src/bot/main.py) is what actually
            # recovers from this, not an on-call human, so this shouldn't
            # page anyone in real time. See that module for the one outcome
            # that does: a post permanently given up on as stale.
            logger.warning(
                "Failed to post after backoff: %s | reply_to=%s | text=%.60r",
                e2, reply_to, text,
            )
            return None

    except tweepy.Forbidden as e:
        # Originally kept at ERROR on the assumption this reliably means a
        # revoked/misconfigured permission. Real incident on 2026-08-21
        # disproved that: the same sm_id hit 403 "not permitted to access
        # this feature" three times over ~45min, then succeeded on its next
        # retry with no manual intervention — i.e. transient X-side
        # flakiness, same as the TweepyException case below. Downgraded to
        # WARNING; the dropped_stale digest (see src/notify/health.py) is
        # the safety net if a 403 ever turns out to be genuinely permanent.
        logger.warning(
            "X API forbidden (check app permissions): %s | reply_to=%s | text=%.60r | raw=%s",
            e, reply_to, text, _raw_response_detail(e),
        )
        return None

    except tweepy.TweepyException as e:
        # Catches everything else, including the 401/503 X intermittently
        # returns on POST /2/tweets — a widely-reported, self-resolving
        # flakiness in X's API (not a credential or config problem on our
        # end), so WARNING rather than ERROR keeps it out of real-time
        # Prowl alerts. The retry loop in src/bot/main.py handles recovery;
        # only a post that's ultimately given up on as stale is alert-worthy.
        logger.warning(
            "X API error: %s | reply_to=%s | text=%.60r | raw=%s",
            e, reply_to, text, _raw_response_detail(e),
        )
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
