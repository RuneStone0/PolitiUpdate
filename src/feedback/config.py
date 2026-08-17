"""Configuration for the monthly feedback-request module."""

import os

# X posting (OAuth 1.0a) — same credentials as src/bot and src/digest
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "")

# Optional: override the year-month to post for, e.g. "2026-08" (mainly for testing)
FEEDBACK_MONTH_OVERRIDE = os.getenv("FEEDBACK_MONTH_OVERRIDE", "").strip()

# When to post: the first Saturday of the month, at/after this local hour,
# in this IANA timezone. Cron can't express "first Saturday" directly, so
# the trigger is expected to fire more often than needed (see README) and
# main.py's scheduling gate decides whether it's actually time to post.
FEEDBACK_TIMEZONE = os.getenv("FEEDBACK_TIMEZONE", "Europe/Copenhagen")
FEEDBACK_HOUR_LOCAL = int(os.getenv("FEEDBACK_HOUR_LOCAL", "18"))

# Local state file (shared data volume) — which year-month was last
# successfully posted, so a re-run for the same month (e.g. a misfiring
# schedule or a manual retry) skips instead of hitting X's duplicate-content
# rejection.
FEEDBACK_STATE_PATH = os.getenv("FEEDBACK_STATE_PATH", "data/feedback_state.json")
