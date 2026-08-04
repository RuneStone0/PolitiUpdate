"""Post to X via the API v2 endpoint using tweepy."""

import logging
import time

import tweepy

from .config import (
    X_API_KEY,
    X_API_SECRET,
    X_ACCESS_TOKEN,
    X_ACCESS_SECRET,
    RATE_LIMIT_BACKOFF,
    DRY_RUN,
)

logger = logging.getLogger(__name__)


def _get_client() -> tweepy.Client:
    """Create an authenticated tweepy Client for API v2."""
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        raise RuntimeError(
            "X API credentials not configured. "
            "Set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET."
        )

    return tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET,
    )


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
