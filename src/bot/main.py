"""Main polling loop — fetch, dedupe, format, post."""

import logging
import os
import signal
import sys
import time
from urllib.parse import urlparse

from . import db
from .config import POLL_INTERVAL_SECONDS, MAX_NEW_ITEMS_PER_POLL, HEALTH_PORT
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


def _handle_signal(signum: int, frame: object) -> None:
    global running
    logger.info("Received signal %d, shutting down gracefully...", signum)
    running = False


def _process_item(raw: dict) -> None:
    """Process a single RSS item: fetch body, save to DB, post to X."""
    guid = raw["guid"]
    title = raw["title"]
    link = raw["link"]

    if db.is_known(guid):
        return

    logger.info("New item: %s", title)

    district, thread_items = fetch_press_release(link)

    if not thread_items:
        logger.warning("No thread items extracted from %s", link)
        db.save_post(guid, title, "", status="failed")
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

    db.save_post(guid, title, latest_body, status="fetching")

    x_post_ids = post_thread(formatted)

    if x_post_ids and x_post_ids[0]:
        db.save_post(guid, title, latest_body, status="posted", x_post_id=x_post_ids[0])
    else:
        db.save_post(guid, title, latest_body, status="failed")


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
            x_post_ids = post_thread(formatted)

            if x_post_ids and x_post_ids[0]:
                db.save_post(guid, title, thread_items[0]["body"],
                             status="posted", x_post_id=x_post_ids[0])
                logger.info("Retry succeeded: %s", title)
            else:
                db.save_post(guid, title, thread_items[0]["body"],
                             status="failed")
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

        new_count = 0
        for raw in items:
            if new_count >= MAX_NEW_ITEMS_PER_POLL:
                break

            try:
                if not db.is_known(raw["guid"]):
                    _process_item(raw)
                    new_count += 1
            except Exception:
                logger.exception("Error processing item: %s", raw.get("title", "?"))
                # Save as failed so we don't retry indefinitely
                try:
                    db.save_post(raw["guid"], raw["title"], "", status="failed")
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
