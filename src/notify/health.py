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
from urllib.parse import urlparse

import requests

from . import config, state
from .prowl import send

# How many dropped-post detail lines to list individually in one digest
# message before summarizing the rest as "(+N more)" — keeps a sustained
# outage from producing an unreadably long Prowl push.
_MAX_DROPPED_POSTS_SHOWN = 10

# Titles the police routinely delete once the case is resolved. A missing-person
# appeal ("Efterlysning") carries the individual's identifying data and is removed
# (GDPR) once they're found — the police also tell media to delete it. So a drop
# here is the expected outcome of the police's own cleanup, not content the bot
# failed to surface. "Efterlyser" (appealing for a suspect/witness) is NOT deleted
# and is intentionally not matched by this marker.
_EXPECTED_DROP_TITLE_MARKERS = ("efterlysning",)

logger = logging.getLogger(__name__)


def _is_expected_drop(title: str) -> bool:
    """True if a dropped post is expected to vanish (police GDPR cleanup of
    missing-person data) and so shouldn't page anyone."""
    lowered = title.lower()
    return any(marker in lowered for marker in _EXPECTED_DROP_TITLE_MARKERS)


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
    """Return one detail line per post permanently given up on (status =
    'dropped_stale') since `since_iso`, oldest first.

    A post only lands in this status after the bot's retry loop has spent
    up to MAX_ARTICLE_AGE_HOURS trying to post it (see src/bot/main.py) —
    it's real content that never made it to X, as opposed to an ordinary
    transient X API hiccup the retry loop is still working through, so
    this is the one posting-failure outcome worth surfacing here. Each
    line carries the sm_id and source article link so a real drop can be
    investigated (or just read) straight from the phone, no SSH needed.
    """
    if not os.path.exists(config.DB_PATH):
        return []
    try:
        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute(
            "SELECT guid, title FROM posts WHERE status = 'dropped_stale' "
            "AND posted_at > ? ORDER BY posted_at ASC",
            (since_iso,),
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        return [f"could not read posts DB at {config.DB_PATH}: {e}"]

    expected = [(g, t) for g, t in rows if _is_expected_drop(t)]
    real = [(g, t) for g, t in rows if not _is_expected_drop(t)]
    if expected:
        logger.info(
            "Suppressing %d dropped post(s) expected to be deleted by the police "
            "(missing-person 'Efterlysning' GDPR cleanup): %s",
            len(expected),
            ", ".join(t for _, t in expected),
        )
    return [
        f"{title} (sm_id={urlparse(guid).fragment or guid}) — {guid}"
        for guid, title in real
    ]


def run_digest() -> None:
    """Periodic (NOTIFY_DIGEST_INTERVAL_HOURS) check for posts permanently
    dropped as stale. The first-ever run only establishes a baseline
    timestamp rather than replaying whatever history predates this check."""
    since = state.read().get("last_digest_check")
    if since is not None:
        dropped = _check_dropped_posts(since)
        if dropped:
            shown = dropped[:_MAX_DROPPED_POSTS_SHOWN]
            lines = "\n".join(f"- {line}" for line in shown)
            more = len(dropped) - len(shown)
            if more:
                lines += f"\n(+{more} more)"
            send(
                f"PolitiUpdate: {len(dropped)} post(s) dropped as stale "
                f"since last check:\n{lines}"
            )
        else:
            logger.info("Dropped-posts digest: nothing dropped since last check")
    state.write({"last_digest_check": datetime.now(timezone.utc).isoformat()})
