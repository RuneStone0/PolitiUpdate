"""Configuration for the weekly digest module."""

import os

# Reuse bot's DB and LLM settings
DB_PATH = os.getenv("DB_PATH", "data/politiupdate.db")

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

# GitHub Gist — same token as x-stats (needs "gist" scope)
GITHUB_GIST_TOKEN = os.getenv("GITHUB_GIST_TOKEN", "")
DIGEST_GIST_ID = os.getenv("DIGEST_GIST_ID", "").strip()

# GitHub Contents API — PAT with "contents: write" on the repo
GITHUB_COMMIT_TOKEN = os.getenv("GITHUB_COMMIT_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "RuneStone0/PolitiUpdate")

# Public URL base for the digest pages (no trailing slash)
DIGEST_BASE_URL = os.getenv("DIGEST_BASE_URL", "https://politiupdate.dk/uge")

# X posting
X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "")

# Optional: override the ISO week number to generate (e.g. "32" for testing past weeks)
DIGEST_WEEK_OVERRIDE = os.getenv("DIGEST_WEEK_OVERRIDE", "").strip()
