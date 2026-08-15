"""Follower sync: follow back new followers, unfollow users who unfollowed us.

Run with:
    python -m src.followers             # sync against the live X API
    python -m src.followers --dry-run   # log intended actions, make no API calls
"""

import argparse
import json
import logging
import sys
import time

import tweepy

from . import config, db
from .client import get_client

logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _user_auth_kwargs(client_type: str) -> dict:
    return {"user_auth": False} if client_type == "oauth2" else {}


def _fetch_all_followers(client: tweepy.Client, client_type: str, own_id: str) -> dict[str, str]:
    """Return {user_id: username} for every current follower, paginated."""
    followers: dict[str, str] = {}
    pagination_token = None

    while True:
        try:
            response = client.get_users_followers(
                own_id,
                max_results=1000,
                pagination_token=pagination_token,
                **_user_auth_kwargs(client_type),
            )
        except tweepy.TooManyRequests:
            logger.warning(
                "Rate limited fetching followers; backing off %ds", config.RATE_LIMIT_BACKOFF
            )
            time.sleep(config.RATE_LIMIT_BACKOFF)
            continue

        for user in response.data or []:
            followers[str(user.id)] = user.username

        pagination_token = (response.meta or {}).get("next_token")
        if not pagination_token:
            break

    return followers


def _follow(client: tweepy.Client, client_type: str, user_id: str, username: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info("[dry-run] would follow back @%s (%s)", username, user_id)
        return True
    try:
        client.follow_user(user_id, **_user_auth_kwargs(client_type))
        logger.info("Followed back @%s (%s)", username, user_id)
        return True
    except tweepy.TooManyRequests:
        logger.warning(
            "Rate limited following @%s; backing off %ds", username, config.RATE_LIMIT_BACKOFF
        )
        time.sleep(config.RATE_LIMIT_BACKOFF)
        return False
    except tweepy.TweepyException:
        logger.exception("Failed to follow @%s (%s)", username, user_id)
        return False


def _unfollow(client: tweepy.Client, client_type: str, user_id: str, username: str, dry_run: bool) -> bool:
    if dry_run:
        logger.info("[dry-run] would unfollow @%s (%s)", username, user_id)
        return True
    try:
        client.unfollow_user(user_id, **_user_auth_kwargs(client_type))
        logger.info("Unfollowed @%s (%s)", username, user_id)
        return True
    except tweepy.TooManyRequests:
        logger.warning(
            "Rate limited unfollowing @%s; backing off %ds", username, config.RATE_LIMIT_BACKOFF
        )
        time.sleep(config.RATE_LIMIT_BACKOFF)
        return False
    except tweepy.TweepyException:
        logger.exception("Failed to unfollow @%s (%s)", username, user_id)
        return False


def sync(dry_run: bool | None = None) -> dict:
    """Reconcile our following list against current followers.

    Follows back new followers and unfollows users who unfollowed us. Tracks
    follow-back status in the DB so a failed follow (e.g. rate limit) is
    retried on the next run instead of being silently dropped.

    Returns a summary dict of counts.
    """
    if dry_run is None:
        dry_run = config.DRY_RUN

    db.init_db()
    client, client_type = get_client()

    me = client.get_me(**_user_auth_kwargs(client_type))
    own_id = str(me.data.id)

    current = _fetch_all_followers(client, client_type, own_id)
    current_ids = set(current)
    known_ids = db.get_known_ids()

    new_ids = current_ids - known_ids
    gone_ids = known_ids - current_ids
    # Still following us, already tracked, but a prior follow-back attempt failed.
    pending_ids = {
        uid
        for uid in current_ids & known_ids
        if (row := db.get_follower(uid)) and not row["followed_back"]
    }

    followed = 0
    unfollowed = 0
    actions = 0

    for user_id in new_ids | pending_ids:
        if actions >= config.MAX_ACTIONS_PER_RUN:
            logger.info(
                "Hit MAX_ACTIONS_PER_RUN (%d); remaining follows deferred to next run",
                config.MAX_ACTIONS_PER_RUN,
            )
            break
        username = current[user_id]
        ok = _follow(client, client_type, user_id, username, dry_run)
        if not dry_run:
            db.upsert_follower(user_id, username, followed_back=ok)
        if ok:
            followed += 1
        actions += 1
        if not dry_run:
            time.sleep(config.ACTION_DELAY_SECONDS)

    for user_id in gone_ids:
        if actions >= config.MAX_ACTIONS_PER_RUN:
            logger.info(
                "Hit MAX_ACTIONS_PER_RUN (%d); remaining unfollows deferred to next run",
                config.MAX_ACTIONS_PER_RUN,
            )
            break
        row = db.get_follower(user_id)
        username = row["username"] if row else "?"
        if _unfollow(client, client_type, user_id, username, dry_run):
            if not dry_run:
                db.remove_follower(user_id)
            unfollowed += 1
        actions += 1
        if not dry_run:
            time.sleep(config.ACTION_DELAY_SECONDS)

    logger.info(
        "Sync complete: %d current followers, %d followed back, %d unfollowed",
        len(current_ids), followed, unfollowed,
    )
    return {
        "followers_count": len(current_ids),
        "followed_back": followed,
        "unfollowed": unfollowed,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Follow back new followers; unfollow users who unfollowed us."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Log intended actions without calling the X API."
    )
    args = parser.parse_args(argv)

    try:
        summary = sync(dry_run=args.dry_run or config.DRY_RUN)
        print(json.dumps(summary, indent=2))
    except Exception:
        logger.exception("Follower sync failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
