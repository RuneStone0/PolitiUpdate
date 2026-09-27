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
from src.newsletter import cases as case_identity
from src.newsletter.generator import rank_highlights
from src.newsletter.generator import summary as clip_summary
from src.newsletter.main import collect_reach

# How many cases the archive page leads with. Deliberately the same helper the
# email briefing uses (``rank_highlights``), so the page and the mail agree on
# what "ugens mest læste" is instead of ranking by two different rules.
HIGHLIGHT_LIMIT = 5
HIGHLIGHT_SUMMARY_CHARS = 180

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
    # Case identity travels with every published row: the page collapses rows
    # that belong to one case (the same press-release page re-announced, or one
    # venue's incident + court outcome), so a case with three updates is one
    # line, not three. Weeks published before this field existed have no `case`
    # and the page falls back to matching on the headline.
    if post.get("case"):
        entry["case"] = post["case"]
        entry["updates"] = post.get("updates", 1)
    if post.get("primary"):
        entry["primary"] = True
    return entry


def annotate_cases(posts_by_category: dict, views: dict[str, int]) -> tuple[int, list[dict]]:
    """Tag every post with its case, and return (number of cases, highlights).

    The clustering and the ranking are the *email* briefing's helpers
    (``src.newsletter.cases`` / ``rank_highlights``) — one definition of "this is
    the same case" and one definition of "most read" for both surfaces, instead
    of the page growing its own slightly-different rules.
    """
    posts = [p for group in posts_by_category.values() for p in group]
    clusters = case_identity.group_by_case(posts)

    entries = []
    for index, cluster in enumerate(clusters):
        key = str(cluster[0].get("x_post_id") or "") or f"case-{index}"
        for post in cluster:
            post["case"] = key
            post["updates"] = len(cluster)
        entry = case_identity.represent(cluster, views)
        entry["post"]["primary"] = True
        entries.append(entry)

    highlights = []
    for entry in rank_highlights(entries, HIGHLIGHT_LIMIT):
        post = entry["post"]
        if not post.get("x_post_id"):
            continue
        highlights.append(
            {
                "title": post["title"],
                "summary": clip_summary(post.get("body", ""), HIGHLIGHT_SUMMARY_CHARS),
                "url": X_TWEET_URL.format(id=post["x_post_id"]),
                "updates": entry["updates"],
                "views": entry["rank_views"],
            }
        )
    return len(clusters), highlights


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


def run(week: int, year: int, dry_run: bool, skip_tweet: bool, reach: bool = True) -> None:
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

    # Reach decides which cases lead the page, exactly as it decides the mail's
    # top five; a failed lookup degrades to a page without the block rather than
    # a wrong one (``collect_reach`` swallows its own errors).
    weeks_posts = [p for group in data["posts_by_category"].values() for p in group]
    views = collect_reach(weeks_posts) if reach else {}
    case_count, highlights = annotate_cases(data["posts_by_category"], views)
    logger.info(
        "Case identity: %d posts -> %d cases (%d with a view count, %d highlights)",
        data["total_posts"], case_count, len(views), len(highlights),
    )
    if highlights:
        print(f"--- {len(highlights)} most-read case(s) ---")
        for h in highlights:
            print(f"- {h['title']} [{h['views']} views, {h['updates']} update(s)]")
        print("---\n")

    digest = {
        "week": week,
        "year": year,
        "total_posts": data["total_posts"],
        "case_count": case_count,
        "highlights": highlights,
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
    parser.add_argument(
        "--no-reach",
        action="store_true",
        help="Skip the X view-count lookup (the page is then published without the most-read block).",
    )
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
        run(week, year, dry_run=args.dry_run, skip_tweet=args.skip_tweet, reach=not args.no_reach)
    except Exception as exc:
        logger.exception("Digest generation failed")
        from src.notify.prowl import send as notify_send

        notify_send(f"PolitiUpdate weekly-post job failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
