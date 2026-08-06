"""Configuration for the X stats app, read from environment variables.

Standalone app settings — deliberately independent of src/bot/config.py so the
stats container doesn't pull in bot-only settings (RSS feed, health port, etc.).
"""

import os

# X API credentials (OAuth 1.0a — Free tier)
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "")

# X API credentials (OAuth 2.0 PKCE — Basic tier or higher)
X_CLIENT_ID = os.getenv("X_CLIENT_ID", "")
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET", "")
X_REDIRECT_URI = os.getenv("X_REDIRECT_URI", "https://localhost:5000/callback")
X_TOKEN_FILE = os.getenv("X_TOKEN_FILE", "data/x_tokens.json")
X_REFRESH_TOKEN = os.getenv("X_REFRESH_TOKEN", "")

# Cache and output
CACHE_SECONDS = int(os.getenv("X_STATS_CACHE_SECONDS", str(7 * 24 * 60 * 60)))
STATS_FILENAME = os.getenv("X_STATS_FILE", "x-stats.json")
USERNAME = os.getenv("X_STATS_USERNAME", "PolitiUpdate")
