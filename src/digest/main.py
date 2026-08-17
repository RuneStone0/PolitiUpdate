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
from src.bot.formatter import _district_prefix as district_short_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

X_TWEET_URL = "https://x.com/PolitiUpdate/status/{id}"


def _entry(post: dict) -> dict:
    entry = {"title": post["title"]}
    if post.get("x_post_id"):
        entry["url"] = X_TWEET_URL.format(id=post["x_post_id"])
    return entry


def _category_items(posts_by_category: dict) -> dict:
    """Return {category: [{title, url?}]} for every post, so the site can let
    readers unfold a category and browse every case posted that week. `url`
    is omitted for posts that predate the x_post_id column being backfilled."""
    return {cat: [_entry(p) for p in posts] for cat, posts in posts_by_category.items()}


UNKNOWN_REGION = "Ukendt"


def _region_items(posts_by_category: dict) -> dict:
    """Return {region: [{title, url?}]} for every post that week, so readers
    can filter to their own police district instead of by category. `region`
    is omitted (bucketed as UNKNOWN_REGION) for posts that predate the
    district column being backfilled."""
    regions: dict[str, list[dict]] = {}
    for posts in posts_by_category.values():
        for post in posts:
            region = district_short_name(post.get("district") or "") or UNKNOWN_REGION
            regions.setdefault(region, []).append(_entry(post))
    return regions


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
    result = generator.generate(data)
    narrative = result["narrative"]
    narrative_html = result["narrative_html"]
    notable = result["notable"]
    print("\n--- Narrative ---")
    print(narrative)
    print("---\n")
    if notable:
        print(f"--- {len(notable)} notable extra case(s) ---")
        for n in notable:
            print(f"- {n['title']}: {n['summary']}")
        print("---\n")

    prev_year, prev_week = builder.adjacent_week(year, week, -1)
    prev_exists = publisher.week_page_exists(prev_year, prev_week)

    digest = {
        "week": week,
        "year": year,
        "total_posts": data["total_posts"],
        "categories": data["categories"],
        "narrative": narrative,
        "narrative_html": narrative_html,
        "notable": notable,
        "category_items": _category_items(data["posts_by_category"]),
        "region_items": _region_items(data["posts_by_category"]),
        "prev_week": {"year": prev_year, "week": prev_week} if prev_exists else None,
        "next_week": None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

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
        publisher.commit_archive(digest)
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
