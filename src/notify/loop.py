"""Persistent scheduling loop for the notify service.

Runs forever (like bot/main.py's polling loop) instead of relying on host
cron, Portainer, or GitHub Actions to trigger separate one-shot containers.
Wakes up periodically and fires the daily health check / weekly stats +
follower check once each has reached its configured time, tracking the
last-fired date in the shared state file so a container restart won't
double-fire a job it already ran today/this week.
"""

import logging
import signal
import time
from datetime import datetime, timezone

from . import config, health, state, weekly

logger = logging.getLogger(__name__)

running = True


def _handle_signal(signum: int, frame: object) -> None:
    global running
    logger.info("Received signal %d, shutting down gracefully...", signum)
    running = False


def _iso_week(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _maybe_run_daily(now: datetime) -> None:
    today = now.date().isoformat()
    if state.read().get("last_daily_run") == today:
        return
    if now.hour < config.DAILY_HOUR_UTC:
        return
    logger.info("Running daily health check")
    health.run()
    state.write({"last_daily_run": today})


def _maybe_run_weekly(now: datetime) -> None:
    this_week = _iso_week(now)
    if state.read().get("last_weekly_run") == this_week:
        return
    if now.weekday() != config.WEEKLY_WEEKDAY or now.hour < config.WEEKLY_HOUR_UTC:
        return
    logger.info("Running weekly stats + follower check")
    weekly.run()
    state.write({"last_weekly_run": this_week})


def _maybe_run_digest(now: datetime) -> None:
    last = state.read().get("last_digest_check")
    if last:
        elapsed_hours = (now - datetime.fromisoformat(last)).total_seconds() / 3600
        if elapsed_hours < config.DIGEST_INTERVAL_HOURS:
            return
    logger.info("Running dropped-posts digest check")
    health.run_digest()


def run() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info(
        "Starting notify loop (daily %02d:00 UTC, weekly %02d:00 UTC on weekday %d, "
        "dropped-posts digest every %dh)",
        config.DAILY_HOUR_UTC, config.WEEKLY_HOUR_UTC, config.WEEKLY_WEEKDAY,
        config.DIGEST_INTERVAL_HOURS,
    )

    while running:
        now = datetime.now(timezone.utc)
        try:
            _maybe_run_daily(now)
            _maybe_run_weekly(now)
            _maybe_run_digest(now)
        except Exception:
            logger.exception("Error in notify loop")

        if running:
            time.sleep(config.LOOP_CHECK_INTERVAL_SECONDS)

    logger.info("Notify loop stopped.")
