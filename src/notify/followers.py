"""Weekly follower-count notification.

Fetches the current X follower count (reusing the x_stats app's API client)
and reports the change since the last run via Prowl. State is persisted to a
private GitHub Gist (see state_gist.py) rather than local disk, so this can
run entirely on GitHub Actions with no local volume.
"""

import logging

from src.x_stats.main import fetch_stats

from . import state_gist
from .prowl import send

logger = logging.getLogger(__name__)


def run() -> None:
    stats = fetch_stats(force_refresh=True)
    followers = stats["followers_count"]

    previous = state_gist.read()
    state_gist.write(stats)

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
