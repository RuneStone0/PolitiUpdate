"""Daily health check across PolitiUpdate services.

Checks the bot's /health endpoint (DB connectivity, RSS reachability, poll
activity) and the shared SQLite DB for a backlog of failed posts. Sends a
Prowl notification only when something looks wrong — silence means healthy.
"""

import logging
import os
import sqlite3

import requests

from . import config
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
