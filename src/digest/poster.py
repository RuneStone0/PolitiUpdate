"""Post the weekly digest link tweet to X."""

import logging
import random

import tweepy

from . import config

logger = logging.getLogger(__name__)

_HEADLINE_TEMPLATES = (
    "Se ugens opdateringer fra Politiet - Uge {week}:",
    "Ugens politiopdateringer er klar - Uge {week}:",
    "Uge {week} hos Politiet - se ugens opdateringer:",
    "Politiets uge {week} er samlet her:",
    "Ugens overblik fra Politiet (uge {week}):",
    "Gik du glip af noget? Ugens politiopdateringer (uge {week}):",
)


def _build_tweet(digest: dict, url: str) -> str:
    week = digest["week"]
    headline = random.choice(_HEADLINE_TEMPLATES).format(week=week)
    return f"{headline}\n\n{url}"


def post_tweet(digest: dict, url: str, dry_run: bool = False) -> str | None:
    """Post the weekly link tweet. Returns the tweet ID, or None on dry run
    or if X reports the exact text as already posted (duplicate content)."""
    text = _build_tweet(digest, url)

    if dry_run:
        print(f"[dry-run] Would post tweet ({len(text)} chars):\n{text}")
        return None

    if not all([config.X_API_KEY, config.X_API_SECRET, config.X_ACCESS_TOKEN, config.X_ACCESS_SECRET]):
        raise RuntimeError(
            "X OAuth 1.0a credentials are not configured. "
            "Set X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET."
        )

    client = tweepy.Client(
        consumer_key=config.X_API_KEY,
        consumer_secret=config.X_API_SECRET,
        access_token=config.X_ACCESS_TOKEN,
        access_token_secret=config.X_ACCESS_SECRET,
    )
    try:
        response = client.create_tweet(text=text)
    except tweepy.errors.Forbidden as exc:
        # Belt-and-suspenders: the primary re-run guard is the state file
        # checked in main.run(). This only catches the case where a retry
        # happens to pick the same random headline template — most re-runs
        # won't land here and rely on the state guard instead. Treat X's
        # duplicate-content rejection as confirmation we already succeeded,
        # not a failure — matches src/bot's proactive-dedup philosophy of
        # not alerting on a rejection that just means "already done".
        if any("duplicate content" in msg.lower() for msg in exc.api_messages):
            logger.warning("X rejected tweet as duplicate content — already posted, treating as done")
            return None
        raise
    tweet_id = response.data["id"]
    logger.info("Posted digest tweet: %s", tweet_id)
    return tweet_id
