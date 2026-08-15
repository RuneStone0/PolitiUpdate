#!/usr/bin/env bash
# Run the follower sync manually (follow back new followers, unfollow lapsed ones).
#
# Usage (from repo root):
#   ./scripts/run-followers.sh              # sync against the live X API
#   ./scripts/run-followers.sh --dry-run    # log intended actions only
#
# Requires `.env.ProdPolitiUpdateBot` with X API creds (OAuth 1.0a preferred).
# Override with FOLLOWERS_ENV_FILE to use a different file.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${FOLLOWERS_ENV_FILE:-.env.ProdPolitiUpdateBot}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found. Create it from .env.example, or set FOLLOWERS_ENV_FILE." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Prefer a local venv (has tweepy/requests); fall back to system python.
if [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  PY="python"
fi

exec "$PY" -m src.followers "$@"
