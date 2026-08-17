"""Main polling loop — fetch, dedupe, format, post."""

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from . import db
from .config import (
    POLL_INTERVAL_SECONDS,
    MAX_NEW_ITEMS_PER_POLL,
    MAX_ARTICLE_AGE_HOURS,
    HEALTH_PORT,
)
from .fetcher import fetch_feed, fetch_press_release
from .formatter import format_post
from .poster import post_thread
from . import health

logger = logging.getLogger(__name__)

running = True
_retry_counter = 0
RETRY_EVERY_POLLS = 80  # ~1 hour at 45s intervals
RETRY_BATCH_SIZE = 3
_HEARTBEAT_EVERY_POLLS = max(1, 300 // max(1, POLL_INTERVAL_SECONDS))  # ~5 min


def _setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    from src.notify.log_handler import install as install_error_alerts

    install_error_alerts()


def _handle_signal(signum: int, frame: object) -> None:
    global running
    logger.info("Received signal %d, shutting down gracefully...", signum)
    running = False


def _article_age_hours(pub_dt: datetime) -> float:
    """Return how many hours old an article is relative to now (UTC)."""
    return (datetime.now(timezone.utc) - pub_dt).total_seconds() / 3600


def _process_item(raw: dict) -> None:
    """Process a single RSS item: fetch body, save to DB, post to X."""
    guid = raw["guid"]
    title = raw["title"]
    link = raw["link"]

    pub_dt: datetime | None = raw.get("pub_dt")
    pub_date_iso: str | None = pub_dt.isoformat() if pub_dt else None

    if db.is_known(guid):
        return

    logger.info("New item: %s", title)

    district, thread_items = fetch_press_release(link)

    if not thread_items:
        logger.warning("No thread items extracted from %s", link)
        db.save_post(guid, title, "", status="failed", pub_date=pub_date_iso)
        return

    # Only post the specific update referenced by the guid's #sm-XXXXX fragment.
    # Each RSS entry targets one update; posting all items would re-post history
    # every time a press release is updated.
    fragment = urlparse(guid).fragment  # e.g. "sm-15078471", or "" if absent
    if fragment:
        matched = [item for item in thread_items if item.get("sm_id") == fragment]
        if matched:
            thread_items = matched

    formatted = [format_post(title, district, item["body"]) for item in thread_items]

    # Store latest body for DB
    latest_body = thread_items[0]["body"]

    dup_guid = db.find_posted_guid(formatted[0])
    if dup_guid:
        # This exact text was already posted under a different guid — the
        # feed re-published the same update. Posting it again would just
        # get rejected by X as duplicate content.
        db.save_post(guid, title, latest_body, status="skipped", pub_date=pub_date_iso,
                     district=district)
        logger.info("Skipping %r — already posted as %s", title, dup_guid)
        return

    db.save_post(guid, title, latest_body, status="fetching", pub_date=pub_date_iso,
                 district=district)

    x_post_ids = post_thread(formatted)

    if x_post_ids and x_post_ids[0]:
        db.save_post(guid, title, latest_body, status="posted",
                     x_post_id=x_post_ids[0], pub_date=pub_date_iso, district=district)
        db.record_posted_texts(guid, zip(formatted, x_post_ids))
    else:
        db.save_post(guid, title, latest_body, status="failed", pub_date=pub_date_iso,
                     district=district)


def _retry_failed() -> int:
    """Retry a batch of previously failed posts. Returns number retried."""
    failed = db.get_failed_posts(limit=RETRY_BATCH_SIZE)
    if not failed:
        return 0

    logger.info("Retrying %d failed posts", len(failed))
    retried = 0

    for post in failed:
        guid = post["guid"]
        title = post["title"]
        link = guid  # guid is the press release URL in the Ritzau feed

        # Skip retrying articles that are too old to be worth posting. A missing
        # pub_date means this row predates the age-gate migration (or otherwise
        # never recorded one) — treat it as stale rather than silently bypassing
        # the gate and retrying it unconditionally.
        pub_date_iso = post.get("pub_date")
        is_stale = True
        age_hours = None
        if pub_date_iso:
            try:
                pub_dt = datetime.fromisoformat(pub_date_iso)
                age_hours = _article_age_hours(pub_dt)
                is_stale = age_hours > MAX_ARTICLE_AGE_HOURS
            except ValueError:
                is_stale = False  # malformed pub_date — fall through to retry

        if is_stale:
            db.save_post(guid, title, "", status="skipped")
            if age_hours is not None:
                logger.info(
                    "Skipping stale failed post (%.1fh old): %s", age_hours, title
                )
            else:
                logger.info(
                    "Skipping failed post with no recorded pub_date: %s", title
                )
            retried += 1
            continue

        try:
            district, thread_items = fetch_press_release(link)
            if not thread_items:
                continue

            fragment = urlparse(guid).fragment
            if fragment:
                matched = [item for item in thread_items if item.get("sm_id") == fragment]
                if matched:
                    thread_items = matched

            formatted = [
                format_post(title, district, item["body"])
                for item in thread_items
            ]

            dup_guid = db.find_posted_guid(formatted[0])
            if dup_guid:
                db.save_post(guid, title, thread_items[0]["body"], status="skipped")
                logger.info(
                    "Retry found %r already posted as %s, giving up", title, dup_guid
                )
                retried += 1
                continue

            x_post_ids = post_thread(formatted)

            if x_post_ids and x_post_ids[0]:
                db.save_post(guid, title, thread_items[0]["body"],
                             status="posted", x_post_id=x_post_ids[0], district=district)
                db.record_posted_texts(guid, zip(formatted, x_post_ids))
                logger.info("Retry succeeded: %s", title)
            else:
                db.save_post(guid, title, thread_items[0]["body"],
                             status="failed", district=district)
        except Exception:
            logger.exception("Retry failed: %s", title)

        retried += 1

    return retried


def run() -> None:
    """Main polling loop."""
    _setup_logging()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Starting PolitiUpdate bot (poll interval: %ds)", POLL_INTERVAL_SECONDS)

    db.init_db()
    if HEALTH_PORT > 0:
        health.start(port=HEALTH_PORT)

    logger.info("Ready — polling feed every %ds (heartbeat every ~5 min)", POLL_INTERVAL_SECONDS)

    _poll_counter = 0
    while running:
        try:
            items = fetch_feed()
        except Exception:
            logger.exception("Error fetching RSS feed")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        # Process newest items first so fresh news is never blocked by a backlog.
        _epoch = datetime.min.replace(tzinfo=timezone.utc)
        items.sort(key=lambda r: r.get("pub_dt") or _epoch, reverse=True)

        new_count = 0
        for raw in items:
            if new_count >= MAX_NEW_ITEMS_PER_POLL:
                break

            # Skip articles that are too old — prevents burst-posting a stale backlog.
            pub_dt: datetime | None = raw.get("pub_dt")
            if pub_dt:
                age_hours = _article_age_hours(pub_dt)
                if age_hours > MAX_ARTICLE_AGE_HOURS:
                    if not db.is_known(raw["guid"]):
                        db.save_post(
                            raw["guid"], raw["title"], "",
                            status="skipped",
                            pub_date=pub_dt.isoformat(),
                        )
                        logger.info(
                            "Skipping old item (%.1fh): %s", age_hours, raw["title"]
                        )
                    continue

            try:
                if not db.is_known(raw["guid"]):
                    _process_item(raw)
                    new_count += 1
            except Exception:
                logger.exception("Error processing item: %s", raw.get("title", "?"))
                # Save as failed so we don't retry indefinitely
                try:
                    db.save_post(raw["guid"], raw["title"], "", status="failed",
                                 pub_date=pub_dt.isoformat() if pub_dt else None)
                except Exception:
                    pass

        if new_count:
            logger.info("Poll complete: %d new items", new_count)

        health.set_last_poll()

        _poll_counter += 1
        if _poll_counter % _HEARTBEAT_EVERY_POLLS == 0:
            logger.info("Heartbeat — still running, %d polls completed", _poll_counter)

        # Periodic retry of failed posts
        global _retry_counter
        _retry_counter += 1
        if _retry_counter >= RETRY_EVERY_POLLS:
            _retry_counter = 0
            _retry_failed()

        if running:
            time.sleep(POLL_INTERVAL_SECONDS)

    health.stop()  # pragma: no cover — only reached on shutdown signal
    logger.info("Bot stopped.")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    run()
