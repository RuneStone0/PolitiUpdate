#!/usr/bin/env bash

# Diagnose why the GitHub Gist publish is failing with 401 Unauthorized.
# Loads the same env file the real script uses, then checks the token.
#
# Usage:
#   ./scripts/debug-gist-token.sh            # uses .env.ProdPolitiUpdateBot
#   X_STATS_ENV_FILE=stack.env ./scripts/debug-gist-token.sh
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${X_STATS_ENV_FILE:-.env.ProdPolitiUpdateBot}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "=== Presence of expected vars in $ENV_FILE (values hidden) ==="
for var in GITHUB_GIST_TOKEN X_STATS_GIST_ID \
           X_API_KEY X_API_SECRET X_ACCESS_TOKEN X_ACCESS_SECRET \
           X_CLIENT_ID X_CLIENT_SECRET X_REFRESH_TOKEN; do
  val="${!var:-}"
  if [[ -n "$val" ]]; then
    echo "$var: set (${#val} chars)"
  else
    echo "$var: EMPTY"
  fi
done
echo

if [[ -z "${GITHUB_GIST_TOKEN:-}" ]]; then
  echo "GITHUB_GIST_TOKEN is EMPTY/not set in $ENV_FILE — the gist publish will fail."
  echo "If X creds are also empty, the whole run fails. Fix the env file first."
  exit 1
fi

echo "X_STATS_GIST_ID: ${X_STATS_GIST_ID:-<not set>}"
echo
echo "Calling GitHub /user to validate the token..."
curl -sS -o /tmp/gh_me.json -w "HTTP %{http_code}\n" \
  -H "Authorization: Bearer $GITHUB_GIST_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user

HTTP_CODE=$(curl -sS -o /tmp/gh_me.json -w "%{http_code}" \
  -H "Authorization: Bearer $GITHUB_GIST_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/user)

echo "--- /user response ---"
cat /tmp/gh_me.json
echo
echo
echo "Calling /gists to verify 'gist' scope..."
curl -sS -o /tmp/gh_gists.json -w "HTTP %{http_code}\n" \
  -H "Authorization: Bearer $GITHUB_GIST_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/gists
