"""Local JSON state for the digest app.

Tracks which ISO week was last successfully posted, mirroring
src/notify/state.py's approach to avoiding double-fires.
"""

import json
import os

from . import config


def read() -> dict:
    if not os.path.exists(config.DIGEST_STATE_PATH):
        return {}
    with open(config.DIGEST_STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write(updates: dict) -> None:
    """Merge `updates` into the persisted state and save it."""
    current = read()
    current.update(updates)
    parent = os.path.dirname(config.DIGEST_STATE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(config.DIGEST_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
