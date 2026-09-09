"""State persistence to prevent double-sending a week.

Mirrors src/digest/state.py: a tiny JSON "last sent" marker on the shared
data volume, so a misfiring schedule or manual re-run for an already-sent
week skips instead of re-sending.
"""

import json
import os

from . import config


def read() -> dict:
    if not os.path.exists(config.NEWSLETTER_STATE_PATH):
        return {}
    try:
        with open(config.NEWSLETTER_STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def write(data: dict) -> None:
    os.makedirs(os.path.dirname(config.NEWSLETTER_STATE_PATH) or ".", exist_ok=True)
    with open(config.NEWSLETTER_STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
