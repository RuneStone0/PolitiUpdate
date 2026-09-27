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

# Public site base (no trailing slash). Mirrors src.digest.publisher's
# SITE_BASE_URL / src.distribute.config: the domain went live 2026-09-22, so the
# canonical base is https://politiupdates.dk (the old github.io URLs 301 there).
# Every briefing links back to that week's published archive page — the owned
# site carries the signup form, so a briefing with no site link is a dead end.
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://politiupdates.dk")

# --- Copy shape -------------------------------------------------------------
# A briefing is a hook, not the record: the week's full list lives on the
# archive page it links to. The delivered week-38 campaign was 136 list items /
# 44 KB of text, which nobody reads to the end. Now it leads with the few most
# *read* stories and then a scannable one-line index, capped here.
NEWSLETTER_HIGHLIGHTS = int(os.getenv("NEWSLETTER_HIGHLIGHTS", "5") or 5)
NEWSLETTER_INDEX_LIMIT = int(os.getenv("NEWSLETTER_INDEX_LIMIT", "20") or 20)
NEWSLETTER_SUMMARY_CHARS = int(os.getenv("NEWSLETTER_SUMMARY_CHARS", "200") or 200)

# --- Reach (which stories were most read) -----------------------------------
# View counts come from fxtwitter (see src/common/x_reach.py) and only decide
# *ranking*; a failed lookup leaves the highlight block out instead of failing
# the send. Set NEWSLETTER_REACH_ENABLED=0 to send the index-only briefing.
REACH_ENABLED = os.getenv("NEWSLETTER_REACH_ENABLED", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "",
)
REACH_DEADLINE_S = float(os.getenv("NEWSLETTER_REACH_DEADLINE_S", "120") or 120)

# Local state file (shared data volume) — which week was last sent, so a
# re-run for the same week skips instead of double-sending.
NEWSLETTER_STATE_PATH = os.getenv("NEWSLETTER_STATE_PATH", "data/newsletter_state.json")
