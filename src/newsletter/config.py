"""Configuration for the weekly region-filtered newsletter module.

Mirrors src/digest/config.py: reads env vars at import time. The sender
(Brevo) integration is wired later once the account/API key and the ``region``
contact attribute exist; the pipeline works in ``--dry-run`` without them.
"""

import os

# Reuse the shared bot DB (same file the bot writes to)
DB_PATH = os.getenv("DB_PATH", "data/politiupdate.db")

# Brevo (set once the account is configured / sending approved)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "PolitiUpdate")
# Name of the Brevo contact attribute that stores a subscriber's region
# (values match src.common.regions labels). Override if named differently.
BREVO_REGION_ATTRIBUTE = os.getenv("BREVO_REGION_ATTRIBUTE", "REGION")

# Optional: override the ISO week number to generate (e.g. "36" for testing)
NEWSLETTER_WEEK_OVERRIDE = os.getenv("NEWSLETTER_WEEK_OVERRIDE", "").strip()

# Local state file (shared data volume) — which week was last sent, so a
# re-run for the same week skips instead of double-sending.
NEWSLETTER_STATE_PATH = os.getenv("NEWSLETTER_STATE_PATH", "data/newsletter_state.json")
