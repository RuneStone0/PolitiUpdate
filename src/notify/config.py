"""Configuration for the notify app, read from environment variables.

Standalone app settings — deliberately independent of src/bot/config.py,
mirroring the src/x_stats and src/digest apps.
"""

import os

# Prowl webhook that receives {"message": "..."} POSTs. No default on purpose
# — the URL itself is unauthenticated and best kept out of the public repo
# (anyone who knows it can POST arbitrary messages to your phone). Set it via
# stack.env / Portainer env vars, same as the other secrets in this app.
PROWL_WEBHOOK_URL = os.getenv("PROWL_WEBHOOK_URL", "")

# The bot service's health endpoint, reachable over the compose network by
# service name (see the `bot` service in docker-compose.yml).
BOT_HEALTH_URL = os.getenv("BOT_HEALTH_URL", "http://bot:8080/health")

# Shared SQLite DB (same volume as the bot service) — used to check for a
# backlog of posts stuck in 'failed' status. notify-daily only — the weekly
# follower check (see followers.py / state_gist.py) has no local dependency.
DB_PATH = os.getenv("DB_PATH", "data/politiupdate.db")
FAILED_POSTS_THRESHOLD = int(os.getenv("NOTIFY_FAILED_POSTS_THRESHOLD", "3"))

REQUEST_TIMEOUT = int(os.getenv("NOTIFY_TIMEOUT", "15"))

# Real-time error alerting: when enabled, a logging handler is attached to the
# bot's root logger that forwards ERROR+ log records (RSS fetch failures,
# item-processing exceptions, etc.) to Prowl as they happen, rather than
# waiting for the next notify-daily sweep. On by default (set NOTIFY_ON_ERROR=0
# to disable, e.g. while PROWL_WEBHOOK_URL is misconfigured and you want to
# avoid alert-fatigue noise).
ERROR_ALERTS_ENABLED = os.getenv("NOTIFY_ON_ERROR", "1").lower() not in ("0", "false", "no")

# Minimum seconds between repeat alerts for the *same* error (deduped by
# logger name + message) — protects against flooding Prowl while an outage
# (e.g. RSS down) keeps logging the same error every poll.
ERROR_ALERT_MIN_INTERVAL = int(os.getenv("NOTIFY_ERROR_MIN_INTERVAL", str(15 * 60)))
