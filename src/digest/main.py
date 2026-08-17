"""Weekly digest orchestrator.

Run with:
    python -m src.digest               # generate + publish + tweet
    python -m src.digest --dry-run     # print output, skip gist/archive/tweet
    python -m src.digest --week 32     # override week number (uses current year)
    python -m src.digest --skip-tweet  # publish but don't post to X
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

from . import builder, config, generator, gist, poster, publisher, state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run(week: int, year: int, dry_run: bool, skip_tweet: bool) -> None:
    week_key = f"{year}-W{week:02d}"
    if not dry_run and state.read().get("last_posted_week") == week_key:
        logger.info("Week %d/%d already posted — skipping", week, year)
        return

    logger.info("Building digest for week %d/%d", week, year)
    data = builder.build(year, week)

    if data["total_posts"] == 0:
        logger.warning("No posts found for week %d/%d — aborting", week, year)
        return

    logger.info(
        "Found %d posts: %s",
        data["total_posts"],
        data["categories"],
    )

    logger.info("Generating narrative via LLM")
    narrative = generator.generate(data)
    print("\n--- Narrative ---")
    print(narrative)
    print("---\n")

    digest = {
        "week": week,
        "year": year,
        "total_posts": data["total_posts"],
        "categories": data["categories"],
        "narrative": narrative,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Include posts_by_category only for archive publishing (stripped before Gist)
    digest_full = {**digest, "posts_by_category": data["posts_by_category"]}

    digest_url = f"{config.DIGEST_BASE_URL}/{year}/{week}"

    if dry_run:
        print(json.dumps(digest, indent=2, ensure_ascii=False))
        poster.post_tweet(digest, digest_url, dry_run=True)
        logger.info("Dry run complete — nothing published")
        return

    logger.info("Publishing digest to GitHub Gist")
    raw_url = gist.publish(digest)
    logger.info("Gist raw URL: %s", raw_url)

    logger.info("Committing archive pages to repo")
    try:
        publisher.commit_archive(digest_full)
    except Exception:
        logger.exception("Archive commit failed — continuing with tweet")

    if not skip_tweet:
        logger.info("Posting link tweet")
        tweet_id = poster.post_tweet(digest, digest_url)
        if tweet_id:
            logger.info("Tweet posted: %s", tweet_id)
    else:
        logger.info("Skipping tweet (--skip-tweet)")

    state.write({"last_posted_week": week_key})
    logger.info("Done")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate and publish the weekly digest.")
    parser.add_argument("--dry-run", action="store_true", help="Print output without publishing or tweeting.")
    parser.add_argument("--skip-tweet", action="store_true", help="Publish but skip the X post.")
    parser.add_argument("--week", type=int, help="ISO week number to generate (default: last completed week).")
    parser.add_argument("--year", type=int, help="Year for --week override (default: current year).")
    args = parser.parse_args(argv)

    if args.week:
        week = args.week
        year = args.year or datetime.now(timezone.utc).year
    elif config.DIGEST_WEEK_OVERRIDE:
        week = int(config.DIGEST_WEEK_OVERRIDE)
        year = args.year or datetime.now(timezone.utc).year
    else:
        year, week = builder.current_week()

    try:
        run(week, year, dry_run=args.dry_run, skip_tweet=args.skip_tweet)
    except Exception as exc:
        logger.exception("Digest generation failed")
        from src.notify.prowl import send as notify_send

        notify_send(f"PolitiUpdate weekly-post job failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
