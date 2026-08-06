"""Publish the stats JSON to a GitHub Gist.

The static website reads `x-stats.json` from a raw GitHub Gist URL, so the
stats container can publish fresh numbers without committing to the repo or
touching GitHub Actions. Requires a Personal Access Token with the `gist`
scope, set as the GITHUB_GIST_TOKEN env var.

Gist must be PUBLIC — the browser fetches its raw URL anonymously (a secret
gist is not readable cross-origin without auth).
"""

import json
import os

import requests

GITHUB_API = "https://api.github.com/gists"

# A gist's first file is used for the raw JSON payload.
GIST_FILENAME = os.getenv("X_STATS_GIST_FILENAME", "x-stats.json")
GIST_DESCRIPTION = os.getenv(
    "X_STATS_GIST_DESCRIPTION",
    "PolitiUpdate X account stats (tweet & follower counts) for the website.",
)
# Optional explicit gist ID to update in place. If unset, we look the gist up
# by matching GIST_DESCRIPTION (or create it on first run).
GIST_ID = os.getenv("X_STATS_GIST_ID", "").strip()


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _find_gist_id(token: str) -> str | None:
    """Look up an existing gist matching our description so we can update it
    in place rather than creating a new gist on every run."""
    try:
        resp = requests.get(
            GITHUB_API,
            headers=_headers(token),
            params={"per_page": 100},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    for gist in resp.json():
        if gist.get("description") == GIST_DESCRIPTION:
            return gist["id"]
    return None


def _existing_filenames(token: str, gist_id: str) -> list[str]:
    """Return the current file names in an existing gist (empty if it can't
    be read). Used so we can null-out files we no longer want."""
    try:
        resp = requests.get(f"{GITHUB_API}/{gist_id}", headers=_headers(token), timeout=30)
        resp.raise_for_status()
        return list(resp.json().get("files", {}).keys())
    except requests.RequestException:
        return []


def publish_stats(stats: dict) -> str:
    """Create or update the stats gist. Returns the raw URL of its JSON file.

    When updating an existing gist, any files other than our target file are
    deleted (set to null) so the gist contains only x-stats.json.
    """
    token = os.getenv("GITHUB_GIST_TOKEN", "")
    if not token:
        raise RuntimeError(
            "GITHUB_GIST_TOKEN is not set. Create a PAT with the 'gist' scope "
            "and set it as an env var on the stats container."
        )

    body = {
        "description": GIST_DESCRIPTION,
        "public": True,
        "files": {GIST_FILENAME: {"content": json.dumps(stats, indent=2, ensure_ascii=False)}},
    }

    gist_id = GIST_ID or _find_gist_id(token)
    if gist_id:
        url = f"{GITHUB_API}/{gist_id}"
        # Delete any leftover files so the gist holds only our target file.
        for name in _existing_filenames(token, gist_id):
            if name != GIST_FILENAME:
                body["files"][name] = None
        resp = requests.patch(url, headers=_headers(token), json=body, timeout=30)
    else:
        url = GITHUB_API
        resp = requests.post(url, headers=_headers(token), json=body, timeout=30)

    resp.raise_for_status()
    data = resp.json()
    raw_url = next(
        (
            f["raw_url"]
            for f in data.get("files", {}).values()
            if f.get("filename") == GIST_FILENAME
        ),
        None,
    )
    if not raw_url:
        raise RuntimeError("Gist created/updated but raw URL could not be determined.")
    return raw_url

