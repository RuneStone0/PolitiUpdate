"""Configuration for the weekly region-filtered newsletter module.

Mirrors ``src/digest/config.py``: reads env vars at import time. The Brevo
integration is wired but *gated* — the pipeline works in ``--dry-run`` without
any credentials; a real send needs ``BREVO_API_KEY`` plus an authenticated
``BREVO_SENDER_EMAIL`` (a verified sending domain).
"""

import os

from src.common.regions import (
    REGION_FYN,
    REGION_HOVEDSTADEN,
    REGION_JYLLAND,
    REGION_NATIONAL,
    REGION_SJAELLAND,
)

# Reuse the shared bot DB (same file the bot writes to)
DB_PATH = os.getenv("DB_PATH", "data/politiupdate.db")

# Brevo (set once the account is configured / sending approved)
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "PolitiUpdate")

# Name of the Brevo contact attribute that stores a subscriber's region
# (values match ``src.common.regions`` labels). Override if named differently.
BREVO_REGION_ATTRIBUTE = os.getenv("BREVO_REGION_ATTRIBUTE", "REGION")

# Region label -> Brevo list id. The public signup form can only add a contact
# to ONE list, so per-region list membership is derived from the REGION
# attribute at send time (see ``sender.sync_region_lists``). List ids created
# 2026-09-10 via the Brevo API; override with env vars if they change.
BREVO_REGION_LISTS = {
    REGION_HOVEDSTADEN: int(os.getenv("BREVO_LIST_HOVEDSTADEN", "3")),
    REGION_SJAELLAND: int(os.getenv("BREVO_LIST_SJAELLAND", "4")),
    REGION_JYLLAND: int(os.getenv("BREVO_LIST_JYLLAND", "5")),
    REGION_FYN: int(os.getenv("BREVO_LIST_FYN", "6")),
    REGION_NATIONAL: int(os.getenv("BREVO_LIST_HELE_LANDET", "7")),
}

# Optional: Brevo custom unsubscribe-page id (24-char). Empty -> Brevo's default
# unsubscribe page is used. Create a branded one in Brevo -> Settings ->
# Campaigns -> Unsubscribe pages, then copy the id from its edit URL.
BREVO_UNSUB_PAGE_ID = os.getenv("BREVO_UNSUB_PAGE_ID", "")

# Optional: override the ISO week number to generate (e.g. "36" for testing)
NEWSLETTER_WEEK_OVERRIDE = os.getenv("NEWSLETTER_WEEK_OVERRIDE", "").strip()

# Local state file (shared data volume) — which week was last sent, so a
# re-run for the same week skips instead of double-sending.
NEWSLETTER_STATE_PATH = os.getenv("NEWSLETTER_STATE_PATH", "data/newsletter_state.json")
