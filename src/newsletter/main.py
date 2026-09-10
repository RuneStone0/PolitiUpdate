"""Weekly region-filtered newsletter orchestrator.

Run with:
    python -m src.newsletter              # build + send campaigns (needs BREVO_API_KEY)
    python -m src.newsletter --dry-run    # print region briefings, send nothing
    python -m src.newsletter --week 36    # override the ISO week (current year)

Per region it (1) syncs the region's contacts into that region's Brevo list,
then (2) creates + sends a Brevo *email campaign* to that list (campaigns carry
the unsubscribe link + stats that transactional email doesn't).
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

from . import builder, config, generator, sender, state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run(week: int, year: int, dry_run: bool) -> None:
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

    results = []
    for region_label, posts in data["regions"].items():
        brief = generator.generate(region_label, posts, week, year)
        print("\n=== %s ===" % region_label)
        print(brief["subject"])
        print(brief["text"])
        print("---")

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
        run(week, year, dry_run=args.dry_run)
    except Exception:
        logger.exception("Newsletter generation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
