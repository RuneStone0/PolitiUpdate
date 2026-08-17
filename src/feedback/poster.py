"""Post the monthly feedback-request tweet to X."""

import logging

import tweepy

from . import config

logger = logging.getLogger(__name__)

_MONTHS_DA = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]


def _build_tweet(year: int, month: int) -> str:
    month_name = _MONTHS_DA[month - 1]
    return (
        f"📢 Feedback-tid ({month_name} {year})! Hvad synes du om @PolitiUpdate, "
        "og hvad kan vi gøre bedre? Hastighed, dækning, format — skriv en kommentar "
        "eller send en DM, vi lytter 👂"
    )


def post_tweet(year: int, month: int, dry_run: bool = False) -> str | None:
    """Post the monthly feedback-request tweet. Returns the tweet ID, or None
    on dry run or if X reports the exact text as already posted (duplicate
    content)."""
    text = _build_tweet(year, month)

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
        # The tweet text is fully determined by year/month, so a re-run for a
        # month we already posted (e.g. a misfiring schedule) always
        # reproduces byte-identical text. Treat X's duplicate-content
        # rejection as confirmation we already succeeded, not a failure —
        # matches src/digest/poster.py's handling of the same case.
        if any("duplicate content" in msg.lower() for msg in exc.api_messages):
            logger.warning("X rejected tweet as duplicate content — already posted, treating as done")
            return None
        raise
    tweet_id = response.data["id"]
    logger.info("Posted feedback-request tweet: %s", tweet_id)
    return tweet_id
