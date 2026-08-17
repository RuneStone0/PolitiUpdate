"""Local JSON state for the feedback app.

Tracks which year-month was last successfully posted, mirroring
src/digest/state.py's approach to avoiding double-fires.
"""

import json
import os

from . import config


def read() -> dict:
    if not os.path.exists(config.FEEDBACK_STATE_PATH):
        return {}
    with open(config.FEEDBACK_STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write(updates: dict) -> None:
    """Merge `updates` into the persisted state and save it."""
    current = read()
    current.update(updates)
    parent = os.path.dirname(config.FEEDBACK_STATE_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(config.FEEDBACK_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
