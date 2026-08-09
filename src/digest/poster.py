"""Post the weekly digest link tweet to X."""

import logging

import tweepy

from . import config

logger = logging.getLogger(__name__)

# X counts all URLs as exactly 23 chars regardless of actual length.
_URL_LENGTH_ON_X = 23


def _build_tweet(digest: dict, url: str) -> str:
    week = digest["week"]
    year = digest["year"]
    total = digest["total_posts"]
    cats = digest["categories"]

    highlights = []
    if cats.get("missing_person"):
        n = cats["missing_person"]
        highlights.append(f"{n} efterlysning{'er' if n != 1 else ''}")
    if cats.get("witness_appeal"):
        n = cats["witness_appeal"]
        highlights.append(f"{n} vidneappel{'ler' if n != 1 else ''}")

    highlights_str = (", ".join(highlights) + " — ") if highlights else ""
    text = (
        f"Ugens politi-overblik (uge {week}): "
        f"{total} opdateringer — "
        f"{highlights_str}"
        f"{url}"
    )

    # X enforces 280 chars, counting the URL as _URL_LENGTH_ON_X.
    # Replace the real URL with a placeholder of that length for the check.
    check = text.replace(url, "x" * _URL_LENGTH_ON_X)
    if len(check) > 280:
        # Trim the highlights from the tweet and keep it simple
        text = f"Ugens politi-overblik (uge {week}): {total} opdateringer → {url}"

    return text


def post_tweet(digest: dict, url: str, dry_run: bool = False) -> str | None:
    """Post the weekly link tweet. Returns the tweet ID, or None on dry run."""
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
    response = client.create_tweet(text=text)
    tweet_id = response.data["id"]
    logger.info("Posted digest tweet: %s", tweet_id)
    return tweet_id
