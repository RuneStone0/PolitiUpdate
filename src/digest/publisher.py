"""Commit the weekly archive pages to the repo via the GitHub Contents API.

Creates/updates two files per run:
  website/uge/{year}/{week}/index.html   — static archive page
  website/uge/{year}/{week}/digest.json  — baked-in data (no runtime fetch)

Pushing to main triggers the GitHub Actions Pages deploy automatically.
Requires a PAT with 'contents: write' scope (GITHUB_COMMIT_TOKEN env var).
"""

import base64
import json
import logging
import textwrap

import requests

from . import config

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.GITHUB_COMMIT_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_file_sha(path: str) -> str | None:
    """Return the current blob SHA for a file, or None if it doesn't exist."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{path}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("sha")
    except requests.RequestException:
        return None


def _put_file(path: str, content: str, message: str) -> None:
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{path}"
    encoded = base64.b64encode(content.encode()).decode()
    body: dict = {
        "message": message,
        "content": encoded,
        "branch": "main",
    }
    sha = _get_file_sha(path)
    if sha:
        body["sha"] = sha

    resp = requests.put(url, headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
    logger.info("Committed %s", path)


def _render_archive_html(digest: dict) -> str:
    week = digest["week"]
    year = digest["year"]
    total = digest["total_posts"]
    cats = digest["categories"]
    narrative = digest.get("narrative", "")
    generated_at = digest.get("generated_at", "")

    missing = cats.get("missing_person", 0)
    witness = cats.get("witness_appeal", 0)
    arrest = cats.get("arrest", 0)
    other = cats.get("other", 0)

    cat_rows = ""
    if missing:
        cat_rows += f'<li><span class="cat-label">Efterlysninger/savnede</span><span class="cat-count">{missing}</span></li>\n'
    if witness:
        cat_rows += f'<li><span class="cat-label">Vidneappeller</span><span class="cat-count">{witness}</span></li>\n'
    if arrest:
        cat_rows += f'<li><span class="cat-label">Anholdelser/sigtelser</span><span class="cat-count">{arrest}</span></li>\n'
    if other:
        cat_rows += f'<li><span class="cat-label">Øvrige meddelelser</span><span class="cat-count">{other}</span></li>\n'

    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="da">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>Uge {week}, {year} — PolitiUpdate</title>
          <link rel="icon" href="/favicon.svg" type="image/svg+xml">
          <link rel="stylesheet" href="/styles.css">
          <link rel="stylesheet" href="/uge/digest.css">
        </head>
        <body>
          <div class="digest-shell">
            <header class="digest-header">
              <a class="back-link" href="/">PolitiUpdate</a>
              <h1>Uge {week}, {year}</h1>
              <p class="digest-meta">{total} politimeddelelser</p>
            </header>

            <main class="digest-main">
              <article class="digest-narrative">
                <p>{narrative}</p>
              </article>

              <section class="digest-breakdown">
                <h2>Fordeling</h2>
                <ul class="cat-list">
                  {cat_rows.strip()}
                </ul>
              </section>
            </main>

            <footer class="digest-footer">
              <p>Genereret med AI &middot; Ikke tilknyttet politiet &middot; Data fra <a href="https://via.ritzau.dk" target="_blank" rel="noopener">Ritzau</a></p>
              <p><a href="/uge">Seneste uges overblik</a></p>
            </footer>
          </div>
        </body>
        </html>
    """)


def commit_archive(digest: dict) -> None:
    """Commit the archive HTML and JSON for the given week to the repo."""
    if not config.GITHUB_COMMIT_TOKEN:
        raise RuntimeError(
            "GITHUB_COMMIT_TOKEN is not set. Create a PAT with 'contents: write' scope."
        )

    week = digest["week"]
    year = digest["year"]
    base = f"website/uge/{year}/{week}"
    commit_msg = f"feat(digest): add week {week}/{year} archive"

    digest_without_posts = {k: v for k, v in digest.items() if k != "posts_by_category"}
    _put_file(
        f"{base}/digest.json",
        json.dumps(digest_without_posts, indent=2, ensure_ascii=False),
        commit_msg,
    )
    _put_file(f"{base}/index.html", _render_archive_html(digest), commit_msg)
    logger.info("Archive for week %s/%s committed to repo", week, year)
