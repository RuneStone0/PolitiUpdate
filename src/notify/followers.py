"""Weekly follower-count notification.

Fetches the current X follower count (reusing the x_stats app's API client)
and reports the change since the last run via Prowl.
"""

import json
import logging
import os

from src.x_stats.main import fetch_stats

from . import config
from .prowl import send

logger = logging.getLogger(__name__)


def _read_previous() -> dict | None:
    if not os.path.exists(config.FOLLOWERS_STATE_PATH):
        return None
    with open(config.FOLLOWERS_STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_state(stats: dict) -> None:
    parent = os.path.dirname(config.FOLLOWERS_STATE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(config.FOLLOWERS_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)


def run() -> None:
    stats = fetch_stats(force_refresh=True)
    followers = stats["followers_count"]

    previous = _read_previous()
    _write_state(stats)

    if previous is None:
        message = f"PolitiUpdate weekly update: tracking followers from a baseline of {followers}."
    else:
        delta = followers - previous["followers_count"]
        sign = "+" if delta >= 0 else ""
        message = (
            f"PolitiUpdate weekly update: {sign}{delta} new followers this week "
            f"({followers} total)."
        )

    logger.info(message)
    send(message)
