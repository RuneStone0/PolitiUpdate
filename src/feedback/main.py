"""Monthly feedback-request orchestrator.

Scheduled for the first Saturday of the month at 18:00 Danish time. Cron
(and similar) can't express "first Saturday of the month" directly, so the
recommended trigger fires more often than needed (see the README) and this
module decides whether it's actually the right moment — mirroring how
src/notify/loop.py self-schedules its daily/weekly jobs instead of trusting
the trigger's cadence.

Run with:
    python -m src.feedback                 # post if it's the scheduled time, else skip
    python -m src.feedback --force         # post now, skipping the scheduling gate
    python -m src.feedback --dry-run       # print output, skip posting and the gate
    python -m src.feedback --month 2026-08 # override year-month, skipping the gate (mainly for testing)
"""

import argparse
import logging
import sys
from datetime import datetime

from zoneinfo import ZoneInfo

from . import config, poster, state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run(year: int, month: int, dry_run: bool) -> None:
    month_key = f"{year}-{month:02d}"
    if not dry_run and state.read().get("last_posted_month") == month_key:
        logger.info("Month %s already posted — skipping", month_key)
        return

    logger.info("Posting feedback request for %s", month_key)
    tweet_id = poster.post_tweet(year, month, dry_run=dry_run)

    if dry_run:
        logger.info("Dry run complete — nothing posted")
        return

    if tweet_id:
        logger.info("Tweet posted: %s", tweet_id)

    state.write({"last_posted_month": month_key})
    logger.info("Done")


def _parse_year_month(value: str) -> tuple[int, int]:
    year_str, month_str = value.split("-", 1)
    return int(year_str), int(month_str)


def _now_local() -> datetime:
    return datetime.now(ZoneInfo(config.FEEDBACK_TIMEZONE))


def _is_first_saturday_at_or_after_hour(now_local: datetime, hour: int) -> bool:
    """True if `now_local` falls on the first Saturday of its month, at or
    after `hour`. Saturdays are 7 days apart, so the first one always lands
    on day 1-7 of the month."""
    return now_local.weekday() == 5 and now_local.day <= 7 and now_local.hour >= hour


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Post the monthly feedback-request tweet.")
    parser.add_argument("--dry-run", action="store_true", help="Print output without posting.")
    parser.add_argument("--month", help="Year-month to post for, e.g. 2026-08 (default: current month).")
    parser.add_argument(
        "--force", action="store_true",
        help="Post now, skipping the first-Saturday/6pm-local scheduling gate.",
    )
    args = parser.parse_args(argv)

    now_local = _now_local()

    if args.month:
        year, month = _parse_year_month(args.month)
    elif config.FEEDBACK_MONTH_OVERRIDE:
        year, month = _parse_year_month(config.FEEDBACK_MONTH_OVERRIDE)
    else:
        year, month = now_local.year, now_local.month

    explicit_month = bool(args.month or config.FEEDBACK_MONTH_OVERRIDE)
    gated = not (explicit_month or args.dry_run or args.force)
    if gated and not _is_first_saturday_at_or_after_hour(now_local, config.FEEDBACK_HOUR_LOCAL):
        logger.info(
            "Not the scheduled post time (first Saturday of the month at/after %02d:00 %s) "
            "— skipping. Now: %s",
            config.FEEDBACK_HOUR_LOCAL, config.FEEDBACK_TIMEZONE, now_local.isoformat(),
        )
        return

    try:
        run(year, month, dry_run=args.dry_run)
    except Exception as exc:
        logger.exception("Feedback-request post failed")
        from src.notify.prowl import send as notify_send

        notify_send(f"PolitiUpdate feedback-post job failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
