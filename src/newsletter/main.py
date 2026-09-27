"""Weekly region-filtered newsletter orchestrator.

Run with:
    python -m src.newsletter              # build + send campaigns (needs BREVO_API_KEY)
    python -m src.newsletter --dry-run    # print region briefings, send nothing
    python -m src.newsletter --week 36    # override the ISO week (current year)

Per region it (1) syncs the region's contacts into that region's Brevo list,
then (2) creates + sends a Brevo *email campaign* to that list (campaigns carry
the unsubscribe link + stats that transactional email doesn't).

Five briefings go out: Hovedstaden, Sjælland, Jylland, Fyn and — last — the
country-wide one ("Hele landet"), which is the fallback audience for
subscribers who have not picked a region (``src/newsletter/routing.py``). A
briefing whose audience is empty is skipped instead of sending a campaign to
nobody.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

from src.common import regions as region_map
from src.common import x_reach

from . import builder, config, generator, routing, sender, state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def collect_reach(posts: list[dict], deadline_s: float | None = None) -> dict[str, int]:
    """View counts for the week's posts (``{}`` if the lookup fails).

    Reach only decides which stories lead the briefing — a failure here must
    never stop a send, so it is logged and swallowed.
    """
    ids = [p.get("x_post_id") for p in posts if p.get("x_post_id")]
    if not ids:
        return {}
    try:
        views = x_reach.fetch_views(
            ids, deadline_s=deadline_s or config.REACH_DEADLINE_S
        )
    except Exception as exc:  # noqa: BLE001 - best-effort presentation data
        logger.warning("Reach lookup failed (%s) — sending the index-only briefing", exc)
        return {}
    logger.info("Reach: %d/%d of the week's posts have a view count", len(views), len(ids))
    return views


def run(week: int, year: int, dry_run: bool, reach: bool | None = None) -> None:
    # A dry run must not touch the network unless reach was asked for
    # explicitly (``--reach``); a real send always fetches it.
    if reach is None:
        reach = config.REACH_ENABLED and not dry_run

    week_key = f"{year}-W{week:02d}"
    if not dry_run and state.read().get("last_sent_week") == week_key:
        logger.info("Week %d/%d already sent — skipping", week, year)
        return

    logger.info("Building region newsletter for week %d/%d", week, year)
    data = builder.build(year, week)

    if data["total_posts"] == 0:
        logger.warning("No posts found for week %d/%d — aborting", week, year)
        return

    logger.info(
        "Found %d posts (%d regional, %d national): %s",
        data["total_posts"], data["totals"]["regional"], data["totals"]["national"],
        {k: len(v) for k, v in data["regions"].items()},
    )

    # Fetch view counts once for the whole week and reuse for every briefing.
    views = collect_reach(data["everything"]) if reach else {}

    briefings = dict(data["regions"])
    briefings[region_map.REGION_NATIONAL] = data["everything"]

    results = []
    for region_label in routing.send_order():
        posts = briefings[region_label]
        brief = generator.generate(region_label, posts, week, year, views=views)
        print("\n=== %s ===" % region_label)
        print(brief["subject"])
        print(brief["text"])
        print("---")
        if brief["highlights"]:
            logger.info(
                "%s: leading with %s",
                region_label,
                ", ".join(f"{h['views']} views: {h['title'][:60]}" for h in brief["highlights"]),
            )

        if not brief["text"]:
            # Nothing for this region (no local and no national posts) — skip
            # rather than email subscribers an empty "0 opdateringer" briefing.
            logger.info("Skipping %r — no posts this week", region_label)
            results.append({"region": region_label, "sent": False, "dry_run": dry_run, "note": "no-posts"})
            continue

        campaign_name = f"PolitiUpdate · {region_label} · uge {week}, {year}"
        if dry_run:
            res = sender.send_region_campaign(
                region_label, brief["subject"], brief["html"], name=campaign_name, dry_run=True
            )
        else:
            # Populate the region list from the REGION attribute before sending,
            # so the campaign reaches everyone who picked this region.
            synced = sender.sync_region_lists(region_label)
            if synced == 0:
                # An empty audience would be a campaign sent to nobody (and a
                # wasted Brevo campaign credit). The country-wide briefing is the
                # fallback, so an empty region here is expected early on.
                logger.info(
                    "Skipping %r — no subscribers on list %s",
                    region_label, sender.list_id_for_region(region_label),
                )
                results.append({
                    "region": region_label, "sent": False, "dry_run": False,
                    "note": "no-subscribers", "synced_contacts": 0,
                })
                continue
            res = sender.send_region_campaign(
                region_label, brief["subject"], brief["html"], name=campaign_name
            )
            res["synced_contacts"] = synced
        results.append(res)

    if not dry_run:
        # Persist the sent marker only after a real (non-preview) send.
        state.write({"last_sent_week": week_key})

    logger.info("Done — processed %d region briefings (dry_run=%s)", len(results), dry_run)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the weekly region-filtered newsletter.")
    parser.add_argument("--dry-run", action="store_true", help="Print region briefings without sending.")
    parser.add_argument("--week", type=int, help="ISO week number (default: last completed week).")
    parser.add_argument("--year", type=int, help="Year for --week override (default: current year).")
    reach = parser.add_mutually_exclusive_group()
    reach.add_argument(
        "--reach",
        dest="reach",
        action="store_true",
        default=None,
        help="Look up X view counts even in --dry-run (needs network), so the preview shows the review.",
    )
    reach.add_argument(
        "--no-reach",
        dest="reach",
        action="store_false",
        help="Skip the view-count lookup; send the index-only briefing.",
    )
    args = parser.parse_args(argv)

    if args.week:
        week = args.week
        year = args.year or datetime.now(timezone.utc).year
    elif config.NEWSLETTER_WEEK_OVERRIDE:
        week = int(config.NEWSLETTER_WEEK_OVERRIDE)
        year = args.year or datetime.now(timezone.utc).year
    else:
        year, week = builder.current_week()

    try:
        run(week, year, dry_run=args.dry_run, reach=args.reach)
    except Exception:
        logger.exception("Newsletter generation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
