"""Publish the weekly digest JSON to a GitHub Gist.

The /uge page and the front-page widget fetch digest.json from this Gist
at runtime, so the data is live without requiring a GitHub Pages redeploy.
Requires a PAT with the 'gist' scope (GITHUB_GIST_TOKEN env var).
"""

import json
import os

import requests

from . import config

GITHUB_API = "https://api.github.com/gists"
GIST_FILENAME = "digest.json"
GIST_DESCRIPTION = "PolitiUpdate weekly digest"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.GITHUB_GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _find_gist_id() -> str | None:
    try:
        resp = requests.get(
            GITHUB_API,
            headers=_headers(),
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


def publish(digest: dict) -> str:
    """Create or update the digest Gist. Returns the raw URL of digest.json."""
    if not config.GITHUB_GIST_TOKEN:
        raise RuntimeError(
            "GITHUB_GIST_TOKEN is not set. Create a PAT with the 'gist' scope."
        )

    body = {
        "description": GIST_DESCRIPTION,
        "public": True,
        "files": {
            GIST_FILENAME: {"content": json.dumps(digest, indent=2, ensure_ascii=False)}
        },
    }

    gist_id = config.DIGEST_GIST_ID or _find_gist_id()
    if gist_id:
        resp = requests.patch(
            f"{GITHUB_API}/{gist_id}", headers=_headers(), json=body, timeout=30
        )
    else:
        resp = requests.post(GITHUB_API, headers=_headers(), json=body, timeout=30)

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
