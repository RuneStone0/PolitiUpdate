"""Weekly job: refresh X stats for the website and report the follower-count
delta via Prowl.

Consolidates what used to be two separately-triggered one-shot jobs
(`x-stats` and the old `notify-weekly`) — both fetched the same X API data,
so there's no reason to run them on separate schedules/containers.
"""

import logging

from src.x_stats.gist import publish_stats
from src.x_stats.main import fetch_stats

from . import state
from .prowl import send

logger = logging.getLogger(__name__)


def run() -> None:
    stats = fetch_stats(force_refresh=True)
    followers = stats["followers_count"]

    try:
        publish_stats(stats)
    except Exception:
        # The website falling a week out of date isn't worth losing the
        # Prowl notification over — log it and carry on.
        logger.exception("Failed to publish X stats to gist — continuing")

    previous = state.read().get("followers_count")
    state.write({"followers_count": followers})

    if previous is None:
        message = f"PolitiUpdate weekly update: tracking followers from a baseline of {followers}."
    else:
        delta = followers - previous
        sign = "+" if delta >= 0 else ""
        message = (
            f"PolitiUpdate weekly update: {sign}{delta} new followers this week "
            f"({followers} total)."
        )

    logger.info(message)
    send(message)
