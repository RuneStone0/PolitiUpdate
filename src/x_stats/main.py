"""Fetch X account stats and cache them for the static website.

Standalone app, separate from the posting bot. Runs as its own container
service (see the `x-stats` entry in docker-compose.yml) and writes
website/x-stats.json for the static site.
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import tweepy

from . import gist as gist_publisher

from .config import (
    CACHE_SECONDS,
    STATS_FILENAME,
    X_ACCESS_SECRET,
    X_ACCESS_TOKEN,
    X_API_KEY,
    X_API_SECRET,
    X_CLIENT_ID,
    X_CLIENT_SECRET,
    X_REDIRECT_URI,
    X_REFRESH_TOKEN,
    X_TOKEN_FILE,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATS_PATH = PROJECT_ROOT / "website" / STATS_FILENAME


def _get_client() -> tweepy.Client:
    if all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        return tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_SECRET,
        )

    if not all([X_CLIENT_ID, X_CLIENT_SECRET]):
        raise RuntimeError(
            "X API credentials are not configured. "
            "Set OAuth 1.0a credentials (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET) "
            "or OAuth 2.0 credentials (X_CLIENT_ID, X_CLIENT_SECRET and valid tokens)."
        )

    tokens = _load_tokens()
    now = int(time.time())
    expires_at = tokens.get("obtained_at", 0) + tokens.get("expires_in", 7200)

    if now > expires_at - 60:
        tokens = _refresh_access_token(tokens["refresh_token"])
        _save_tokens(tokens)

    return tweepy.Client(bearer_token=tokens["access_token"])


def _load_tokens() -> dict:
    if X_REFRESH_TOKEN:
        return _refresh_access_token(X_REFRESH_TOKEN)
    if not Path(X_TOKEN_FILE).exists():
        raise RuntimeError(
            f"Token file not found at {X_TOKEN_FILE}. Run 'python -m src.bot.auth' or set X_REFRESH_TOKEN."
        )
    with open(X_TOKEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_tokens(tokens: dict) -> None:
    Path(X_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(X_TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)


def _refresh_access_token(refresh_token: str) -> dict:
    oauth2 = tweepy.OAuth2UserHandler(
        client_id=X_CLIENT_ID,
        client_secret=X_CLIENT_SECRET,
        redirect_uri=X_REDIRECT_URI,
        scope=["tweet.read", "users.read", "offline.access"],
    )
    tokens = oauth2.refresh_token(
        "https://api.x.com/2/oauth2/token",
        refresh_token=refresh_token,
    )
    tokens["obtained_at"] = int(time.time())
    return tokens


def _read_cache() -> dict | None:
    if not STATS_PATH.exists():
        return None
    age = time.time() - STATS_PATH.stat().st_mtime
    if age > CACHE_SECONDS:
        return None
    with open(STATS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_cache(data: dict) -> None:
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def fetch_stats(force_refresh: bool = False) -> dict:
    cached = None if force_refresh else _read_cache()
    if cached is not None:
        print("Using cached X stats from", STATS_PATH)
        return cached

    client = _get_client()
    response = client.get_me(user_fields=["public_metrics"])
    if response.data is None:
        raise RuntimeError("Failed to load user data from X API")

    metrics = response.data.public_metrics
    stats = {
        "username": response.data.username,
        "tweet_count": metrics.get("tweet_count", 0),
        "followers_count": metrics.get("followers_count", 0),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_cache(stats)
    print("Fetched and cached X stats to", STATS_PATH)
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fetch X account stats and publish them to a GitHub Gist for the website."
    )
    parser.add_argument("--refresh", action="store_true", help="Force refresh the cached stats.")
    parser.add_argument(
        "--skip-gist",
        action="store_true",
        help="Fetch stats but do NOT publish to a GitHub Gist.",
    )
    args = parser.parse_args(argv)

    try:
        stats = fetch_stats(force_refresh=args.refresh)
        print(json.dumps(stats, indent=2, ensure_ascii=False))

        if args.skip_gist:
            print("Skipping gist publish (--skip-gist).")
        else:
            raw_url = gist_publisher.publish_stats(stats)
            print("Published stats to gist. Raw URL:", raw_url)
    except Exception as exc:
        print("ERROR:", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

