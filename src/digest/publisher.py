"""Commit the weekly archive pages to the repo via the GitHub Contents API.

Creates/updates two files per run:
  website/uge/{year}/{week}/index.html   — static archive page
  website/uge/{year}/{week}/digest.json  — baked-in data (no runtime fetch)

Pushing to main triggers the GitHub Actions Pages deploy automatically.
Requires a PAT with 'contents: write' scope (GITHUB_COMMIT_TOKEN env var).
"""

import base64
import html
import json
import logging
import textwrap

import requests

from . import config

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

CATEGORY_LABELS = {
    "missing_person": "Efterlysninger/savnede",
    "witness_appeal": "Vidneappeller",
    "arrest": "Anholdelser/sigtelser",
    "other": "Øvrige meddelelser",
}


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


def _render_cat_items(items: list[dict]) -> str:
    rows = []
    for item in items:
        title = html.escape(item["title"])
        if item.get("url"):
            rows.append(
                f'<li><a href="{html.escape(item["url"])}" target="_blank" rel="noopener">{title}</a></li>'
            )
        else:
            rows.append(f"<li><span>{title}</span></li>")
    return "\n".join(rows)


def _render_accordion(cats: dict, category_items: dict) -> str:
    blocks = []
    for cat, label in CATEGORY_LABELS.items():
        count = cats.get(cat, 0)
        if not count:
            continue
        items_html = _render_cat_items(category_items.get(cat, []))
        blocks.append(
            f'<details class="cat-item">\n'
            f"  <summary><span class=\"cat-label\">{label}</span>"
            f'<span class="cat-count">{count}</span></summary>\n'
            f'  <ul class="cat-item-list">\n    {items_html}\n  </ul>\n'
            f"</details>"
        )
    return "\n".join(blocks)


def _render_archive_html(digest: dict) -> str:
    week = digest["week"]
    year = digest["year"]
    total = digest["total_posts"]
    cats = digest["categories"]
    narrative = digest.get("narrative", "")
    generated_at = digest.get("generated_at", "")
    sources = digest.get("sources", [])
    notable = digest.get("notable", [])
    category_items = digest.get("category_items", {})

    accordion_html = _render_accordion(cats, category_items)

    source_rows = "\n".join(
        f'<li><a href="{html.escape(s["url"])}" target="_blank" rel="noopener">{html.escape(s["title"])}</a></li>'
        for s in sources
    )
    sources_section = (
        f"""
              <section class="digest-sources">
                <h2>Kilder</h2>
                <ul class="source-list">
                  {source_rows}
                </ul>
              </section>
"""
        if source_rows
        else ""
    )

    notable_rows = "\n".join(
        f'<li><a href="{html.escape(n["url"])}" target="_blank" rel="noopener">{html.escape(n["title"])}</a>'
        f'<p>{html.escape(n["summary"])}</p></li>'
        for n in notable
    )
    notable_section = (
        f"""
              <section class="digest-notable">
                <h2>Andre bemærkelsesværdige sager</h2>
                <ul class="notable-list">
                  {notable_rows}
                </ul>
              </section>
"""
        if notable_rows
        else ""
    )

    return textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="da">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>Uge {week}, {year} — PolitiUpdate</title>
          <link rel="icon" href="../../../favicon.svg" type="image/svg+xml">
          <link rel="stylesheet" href="../../../styles.css">
          <link rel="stylesheet" href="../../digest.css">
        </head>
        <body>
          <div class="digest-shell">
            <header class="digest-header">
              <a class="back-link" href="../../../">PolitiUpdate</a>
              <h1>Uge {week}, {year}</h1>
              <p class="digest-meta">{total} Opdateringer</p>
            </header>

            <main class="digest-main">
              <article class="digest-narrative">
                <p>{narrative}</p>
              </article>
{sources_section}{notable_section}
              <section class="digest-breakdown">
                <h2>Statistik</h2>
                <div class="cat-list">
                  {accordion_html}
                </div>
              </section>
            </main>

            <footer class="digest-footer">
              <p>Ikke tilknyttet politiet &middot; Data fra <a href="https://via.ritzau.dk" target="_blank" rel="noopener">Ritzau</a></p>
              <p><a href="../../">Seneste uges overblik</a></p>
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
