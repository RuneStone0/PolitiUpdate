"""Local JSON state for the notify service.

Tracks the last known X follower count and which daily/weekly runs have
already fired, so a container restart doesn't double-fire a job it already
ran today/this week. Lives on the same shared data volume as bot's DB —
notify runs as a persistent container on the same host, so there's no need
to persist this remotely (see docs/ for the earlier GitHub Actions /
GitHub Gist approach this replaced).
"""

import json
import os

from . import config


def read() -> dict:
    if not os.path.exists(config.STATE_PATH):
        return {}
    with open(config.STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write(updates: dict) -> None:
    """Merge `updates` into the persisted state and save it."""
    current = read()
    current.update(updates)
    parent = os.path.dirname(config.STATE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(config.STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
