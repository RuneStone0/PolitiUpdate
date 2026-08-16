"""Configuration for the followers app, read from environment variables.

Standalone app settings — deliberately independent of src/bot/config.py so the
followers container doesn't pull in bot-only settings (RSS feed, health port, etc.),
matching the pattern in src/x_stats/config.py.
"""

import os

# X API credentials (OAuth 1.0a — Free tier). Preferred: follow/unfollow work
# under the app's full read+write access without needing extra OAuth 2.0 scopes.
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "")

# X API credentials (OAuth 2.0 PKCE — Basic tier+). Requires a token authorized
# with follows.read/follows.write scopes (see src/followers/client.py SCOPES).
X_CLIENT_ID = os.getenv("X_CLIENT_ID", "")
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET", "")
X_REDIRECT_URI = os.getenv("X_REDIRECT_URI", "https://localhost:5000/callback")
X_TOKEN_FILE = os.getenv("X_TOKEN_FILE", "data/x_tokens.json")
X_REFRESH_TOKEN = os.getenv("X_REFRESH_TOKEN", "")

DB_PATH = os.getenv("FOLLOWERS_DB_PATH", "data/followers.db")

# Log intended actions without calling the X API.
DRY_RUN = os.getenv("FOLLOWERS_DRY_RUN", "").lower() in ("1", "true", "yes")

# Seconds to sleep between individual follow/unfollow API calls.
ACTION_DELAY_SECONDS = int(os.getenv("FOLLOWERS_ACTION_DELAY_SECONDS", "2"))

# Safety valve: max follow/unfollow actions per run. Remaining work is picked
# up on the next scheduled run rather than risking a rate-limit storm.
MAX_ACTIONS_PER_RUN = int(os.getenv("FOLLOWERS_MAX_ACTIONS_PER_RUN", "50"))

# How long to back off after hitting X rate limits (seconds).
RATE_LIMIT_BACKOFF = int(os.getenv("RATE_LIMIT_BACKOFF", "900"))
