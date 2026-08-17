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

UNKNOWN_REGION = "Ukendt"

STATS_TOGGLE_SCRIPT = """\
    <script>
      document.querySelectorAll('#stats-section .sort-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          document.querySelectorAll('#stats-section .sort-btn').forEach(function (b) {
            b.classList.toggle('active', b === btn);
          });
          var sort = btn.dataset.sort;
          document.querySelector('#stats-section [data-panel="category"]').hidden = sort !== 'category';
          document.querySelector('#stats-section [data-panel="region"]').hidden = sort !== 'region';
        });
      });
    </script>
"""


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


def _render_accordion(groups: list[tuple[str, list[dict]]]) -> str:
    """groups: [(label, items)] in the order they should appear, already
    filtered to non-empty groups."""
    blocks = []
    for label, items in groups:
        items_html = _render_cat_items(items)
        blocks.append(
            f'<details class="cat-item">\n'
            f'  <summary><span class="cat-count">{len(items)}</span>'
            f'<span class="cat-label">{html.escape(label)}</span></summary>\n'
            f'  <ul class="cat-item-list">\n    {items_html}\n  </ul>\n'
            f"</details>"
        )
    return "\n".join(blocks)


def _category_groups(cats: dict, category_items: dict) -> list[tuple[str, list[dict]]]:
    return [
        (label, category_items.get(cat, []))
        for cat, label in CATEGORY_LABELS.items()
        if cats.get(cat, 0)
    ]


def _region_groups(region_items: dict) -> list[tuple[str, list[dict]]]:
    known = sorted((label, items) for label, items in region_items.items() if label != UNKNOWN_REGION)
    unknown = [(UNKNOWN_REGION, region_items[UNKNOWN_REGION])] if UNKNOWN_REGION in region_items else []
    return known + unknown


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
    region_items = digest.get("region_items", {})

    category_accordion_html = _render_accordion(_category_groups(cats, category_items))
    region_accordion_html = _render_accordion(_region_groups(region_items))

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
              <section class="digest-breakdown" id="stats-section">
                <div class="stats-header">
                  <h2>Statistik</h2>
                  <div class="sort-toggle" role="group" aria-label="Sortér efter">
                    <button type="button" class="sort-btn active" data-sort="category">Kategori</button>
                    <button type="button" class="sort-btn" data-sort="region">Region</button>
                  </div>
                </div>
                <div class="cat-list" data-panel="category">
                  {category_accordion_html}
                </div>
                <div class="cat-list" data-panel="region" hidden>
                  {region_accordion_html}
                </div>
              </section>
            </main>

            <footer class="digest-footer">
              <p>Ikke tilknyttet politiet &middot; Data fra <a href="https://via.ritzau.dk" target="_blank" rel="noopener">Ritzau</a></p>
              <p><a href="../../">Seneste uges overblik</a></p>
            </footer>
          </div>
{STATS_TOGGLE_SCRIPT}\
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
