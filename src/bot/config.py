"""Configuration from environment variables with sensible defaults."""

import os

RSS_FEED_URL = os.getenv(
    "RSS_FEED_URL",
    "https://via.ritzau.dk/rss/short-messages/latest",
)

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

DB_PATH = os.getenv("DB_PATH", "data/politiupdate.db")

# X API credentials (OAuth 1.0a — required for Free tier posting)
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "")

# X API credentials (OAuth 2.0 PKCE — needs Basic tier or higher)
X_CLIENT_ID = os.getenv("X_CLIENT_ID", "")
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET", "")
X_REDIRECT_URI = os.getenv("X_REDIRECT_URI", "https://localhost:5000/callback")
X_TOKEN_FILE = os.getenv("X_TOKEN_FILE", "data/x_tokens.json")
X_REFRESH_TOKEN = os.getenv("X_REFRESH_TOKEN", "")

# Toggle full-length posts (X Premium needed for >280 chars).
# Without Premium the formatter condenses via LLM (if enabled) or truncates cleanly.
X_PRO = os.getenv("X_PRO", "").lower() in ("1", "true", "yes")

# Post length: 280 without Premium, 25000 with Premium. Set to 0 to disable truncation entirely.
POST_MAX_CHARS = int(os.getenv("POST_MAX_CHARS", "280"))
if X_PRO:
    POST_MAX_CHARS = int(os.getenv("POST_MAX_CHARS", "25000"))

# LLM summarization: condense posts > POST_MAX_CHARS instead of hard truncation.
# Uses DeepSeek API (OpenAI-compatible). Optional but recommended without X_PRO.
LLM_ENABLED = os.getenv("LLM_ENABLED", "").lower() in ("1", "true", "yes")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))

# How long to back off after hitting X rate limits (seconds)
RATE_LIMIT_BACKOFF = int(os.getenv("RATE_LIMIT_BACKOFF", "900"))

# Max items to process per poll (safety valve)
MAX_NEW_ITEMS_PER_POLL = int(os.getenv("MAX_NEW_ITEMS_PER_POLL", "5"))

# Health check HTTP server port (0 = disabled)
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))
