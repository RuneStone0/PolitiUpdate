"""Daily health check across PolitiUpdate services.

Checks the bot's /health endpoint (DB connectivity, RSS reachability, poll
activity) and the shared SQLite DB for a backlog of failed posts. Sends a
Prowl notification only when something looks wrong — silence means healthy.

Also runs the periodic dropped-posts digest (see run_digest() below) — a
separate, coarser check on its own cadence (NOTIFY_DIGEST_INTERVAL_HOURS),
distinct from this module's daily run().
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone

import requests

from . import config, state
from .prowl import send

logger = logging.getLogger(__name__)


def _check_bot_health() -> list[str]:
    """Return problem descriptions for the bot service (empty if healthy)."""
    try:
        resp = requests.get(config.BOT_HEALTH_URL, timeout=config.REQUEST_TIMEOUT)
    except requests.RequestException as e:
        return [f"bot service unreachable at {config.BOT_HEALTH_URL}: {e}"]

    try:
        body = resp.json()
    except ValueError:
        return [f"bot /health returned a non-JSON response (status {resp.status_code})"]

    if resp.status_code == 200 and body.get("healthy"):
        return []

    checks = body.get("checks", {})
    failing = {
        k: v
        for k, v in checks.items()
        if k in ("db", "rss") and v != "ok" and not str(v).startswith("reachable")
    }
    detail = "; ".join(f"{k}: {v}" for k, v in failing.items()) or f"status {resp.status_code}"
    return [f"bot service unhealthy — {detail}"]


def _check_failed_posts() -> list[str]:
    """Return a problem description if too many posts are stuck as 'failed'."""
    if not os.path.exists(config.DB_PATH):
        return []
    try:
        conn = sqlite3.connect(config.DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM posts WHERE status = 'failed'").fetchone()[0]
        conn.close()
    except sqlite3.Error as e:
        return [f"could not read posts DB at {config.DB_PATH}: {e}"]

    if count >= config.FAILED_POSTS_THRESHOLD:
        return [f"{count} posts stuck in 'failed' status (threshold {config.FAILED_POSTS_THRESHOLD})"]
    return []


def run() -> None:
    problems = _check_bot_health() + _check_failed_posts()

    if not problems:
        logger.info("Daily health check: all services OK")
        return

    message = "PolitiUpdate daily health check found issues:\n" + "\n".join(
        f"- {p}" for p in problems
    )
    logger.warning(message)
    send(message)


def _check_dropped_posts(since_iso: str) -> list[str]:
    """Return a summary of posts permanently given up on (status =
    'dropped_stale') since `since_iso`.

    A post only lands in this status after the bot's retry loop has spent
    up to MAX_ARTICLE_AGE_HOURS trying to post it (see src/bot/main.py) —
    it's real content that never made it to X, as opposed to an ordinary
    transient X API hiccup the retry loop is still working through, so
    this is the one posting-failure outcome worth surfacing here.
    """
    if not os.path.exists(config.DB_PATH):
        return []
    try:
        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute(
            "SELECT title FROM posts WHERE status = 'dropped_stale' AND posted_at > ?",
            (since_iso,),
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        return [f"could not read posts DB at {config.DB_PATH}: {e}"]

    if not rows:
        return []
    titles = [r[0] for r in rows]
    shown = "; ".join(titles[:5])
    more = f" (+{len(titles) - 5} more)" if len(titles) > 5 else ""
    plural = "post" if len(titles) == 1 else "posts"
    return [f"{len(titles)} {plural} dropped as stale since last check: {shown}{more}"]


def run_digest() -> None:
    """Periodic (NOTIFY_DIGEST_INTERVAL_HOURS) check for posts permanently
    dropped as stale. The first-ever run only establishes a baseline
    timestamp rather than replaying whatever history predates this check."""
    since = state.read().get("last_digest_check")
    if since is not None:
        problems = _check_dropped_posts(since)
        if problems:
            send("PolitiUpdate: " + "; ".join(problems))
        else:
            logger.info("Dropped-posts digest: nothing dropped since last check")
    state.write({"last_digest_check": datetime.now(timezone.utc).isoformat()})
