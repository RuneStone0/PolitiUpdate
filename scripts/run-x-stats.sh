#!/usr/bin/env bash
# Run the X stats fetcher manually and publish to the gist.
#
# Usage (from repo root):
#   ./scripts/run-x-stats.sh            # uses cached stats (no X API call) if fresh
#   ./scripts/run-x-stats.sh --refresh  # force a fresh fetch from X, then publish
#
# Requires `.env.ProdPolitiUpdateBot` with X OAuth 1.0a creds and GITHUB_GIST_TOKEN.
# Override with X_STATS_ENV_FILE to use a different file.
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${X_STATS_ENV_FILE:-.env.ProdPolitiUpdateBot}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found. Create it from .env.example, or set X_STATS_ENV_FILE." >&2
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

exec "$PY" -m src.x_stats "$@"
