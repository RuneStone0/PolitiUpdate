"""Commit the weekly archive pages to the repo via the GitHub Contents API.

Creates/updates three files per run:
  website/uge/{year}/{week}/index.html   — static archive page
  website/uge/{year}/{week}/digest.json  — baked-in data (no runtime fetch)
  website/sitemap.xml                    — keeps this week discoverable

Pushing to main triggers the GitHub Actions Pages deploy automatically.
Requires a PAT with 'contents: write' scope (GITHUB_COMMIT_TOKEN env var).
"""

import base64
import html
import json
import logging
import os
import re
import textwrap
from datetime import date

import requests

from . import config

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

# Public site root — used for canonical/Open Graph URLs on the archive pages so
# a shared digest link renders a proper preview card (Reddit, Facebook, X).
#
# Since 2026-09-22 the site's canonical address is the custom domain
# `politiupdates.dk` (delegated at the .dk registry, HTTPS enforced, serving 200
# with a valid certificate); the old `runestone0.github.io/PolitiUpdate` URLs
# 301 here. `os.getenv` mirrors src/distribute/config.py so a preview/dry run can
# point the template at another host.
DEFAULT_SITE_BASE_URL = "https://politiupdates.dk"
SITE_BASE_URL = os.getenv("SITE_BASE_URL", DEFAULT_SITE_BASE_URL).rstrip("/")

# --- Sitemap -----------------------------------------------------------------
# The sitemap used to be hand-maintained, so it rotted the same way every
# template-only change on this site has: week 37 was published on 2026-09-13 and
# the live sitemap still listed only weeks 33–36 four days later. The weekly
# archive IS the site's only indexable content (there are no per-release pages),
# so an unlisted week is a week search engines are never told about — and the
# backfill script discovers weeks from this same file, so a stale list also hid
# the one page that needed re-rendering. The digest run now rewrites the sitemap
# in the same commit batch that publishes the week.
SITEMAP_PATH = "website/sitemap.xml"
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SITEMAP_STATIC_ENTRIES = (
    (f"{SITE_BASE_URL}/", "daily", "1.0"),
    (f"{SITE_BASE_URL}/uge/", "weekly", "0.8"),
)
WEEK_CHANGEFREQ = "monthly"
WEEK_PRIORITY = "0.6"

_URL_BLOCK_RE = re.compile(r"^[ \t]*<url>.*?</url>", re.DOTALL | re.MULTILINE)
_LOC_RE = re.compile(r"<loc>\s*([^<]*?)\s*</loc>")
_LASTMOD_RE = re.compile(r"<lastmod>\s*([^<]*?)\s*</lastmod>")
_WEEK_LOC_RE = re.compile(r"/uge/(\d{4})/(\d{1,2})/?$")

CATEGORY_LABELS = {
    "missing_person": "Efterlysninger/savnede",
    "witness_appeal": "Vidneappeller",
    "arrest": "Anholdelser/sigtelser",
    "other": "Øvrige meddelelser",
}

UNKNOWN_REGION = "Ukendt"

# --- Newsletter signup (Brevo native form) -----------------------------------
# The signup form is Brevo's native embed, which means the markup is ours and
# there is no Forms API to fetch it from — the same block therefore exists in
# three places: website/index.html (landing page), website/uge/index.html
# (archive index, rendered client-side) and this template (every week page).
# NEWSLETTER_FORM_ACTION is the single identifier of "our form"; the landing
# page and this template must always agree on it, and tests/test_archive_signup.py
# fails if they drift.
NEWSLETTER_FORM_ACTION = (
    "https://2e5ae89a.sibforms.com/serve/"
    "MUIFAO_V6U8LWa9W0x0khEvDMVcOsFqcOzdxxNaavIe1y70gxaQ19XyGVj3UCCEsIv0vRNeDBJ6WbBMtv3YkgoXyqKc"
    "El8Jx4LtwJu84r1ORITSE6qiNoDJOmFx0UDcxQe2ScbsG7PSdQqbUNl5JzLL2Ext4h7qKWWM2c0uvOUWjltpVS_HoVSd8"
    "antFv8-Kdbx7GGdi24KZuoURiw=="
)
SIBFORMS_STYLESHEET = "https://sibforms.com/forms/end-form/build/sib-styles.css"
SIBFORMS_SCRIPT = "https://sibforms.com/forms/end-form/build/main.js"

# Kept in sync with website/index.html — see NEWSLETTER_FORM_ACTION above.
_SIGNUP_FORM_HTML = """\
<div class="sib-form">
  <div id="sib-form-container" class="sib-form-container">
    <div id="error-message" class="sib-form-message-panel" style="font-family:Helvetica, sans-serif; font-size:16px; text-align:left; color:#661d1d; background-color:#ffeded; border-color:#ff4949; border-radius:8px;">
      <div class="sib-form-message-panel__text sib-form-message-panel__text--center">
        <span class="sib-form-message-panel__inner-text">Din tilmelding kunne ikke gemmes. Prøv igen.</span>
      </div>
    </div>
    <div id="success-message" class="sib-form-message-panel" style="font-family:Helvetica, sans-serif; font-size:16px; text-align:left; color:#085229; background-color:#e7faf0; border-color:#13ce66; border-radius:8px;">
      <div class="sib-form-message-panel__text sib-form-message-panel__text--center">
        <span class="sib-form-message-panel__inner-text">Din tilmelding er gennemført.</span>
      </div>
    </div>
    <div id="sib-container" class="sib-container--large sib-container--vertical" style="direction:ltr">
      <form id="sib-form" method="POST" action="__ACTION__" data-type="subscription">
        <div style="padding: 8px 0;">
          <div class="sib-input sib-form-block">
            <div class="form__entry entry_block">
              <div class="form__label-row">
                <label class="entry__label" for="EMAIL" data-required="*">E-mailadresse</label>
                <div class="entry__field">
                  <input class="input" type="text" id="EMAIL" name="EMAIL" autocomplete="off" value="" placeholder="din@email.dk" data-required="true" required />
                </div>
              </div>
              <label class="entry__error entry__error--primary"></label>
              <label class="entry__specification">Indtast en gyldig e-mailadresse. Eks. abc@xyz.dk</label>
            </div>
          </div>
        </div>
        <div style="padding: 8px 0;">
          <div class="sib-form-block" style="text-align: left">
            <button class="sib-form-block__button sib-form-block__button-with-loader" form="sib-form" type="submit">Tilmeld</button>
          </div>
        </div>
        <input type="text" name="email_address_check" value="" class="input--hidden">
        <input type="hidden" name="locale" value="en">
      </form>
    </div>
  </div>
</div>"""

# The archive-page signup block. Every page a visitor can land on from a shared
# link must be able to convert that visitor into a subscriber: the digest
# archives are exactly where the weekly tweet / Reddit / Facebook posts point,
# and until this block existed they carried no signup path at all (a visitor had
# to navigate back to the landing page to subscribe).
_SIGNUP_SECTION = """\
<section class="digest-signup">
  <p class="eyebrow">Nyhedsbrev</p>
  <h2>F&aring; ugens overblik i din indbakke</h2>
  <p class="digest-signup-copy">Gratis ugentligt overblik over politiets opdateringer fra hele Danmark. Tilmelding tager 10 sekunder, og du kan altid afmelde igen.</p>
__FORM__
</section>"""


def render_signup_section(indent: str = "") -> str:
    """Return the newsletter signup block, optionally indented for a template.

    Imported by the digest template (every future week page) and reused by
    scripts/backfill-archive-pages.py (already-published weeks).
    """
    block = _SIGNUP_SECTION.replace("__FORM__", _SIGNUP_FORM_HTML)
    block = block.replace("__ACTION__", NEWSLETTER_FORM_ACTION)
    block = textwrap.dedent(block)
    return textwrap.indent(block, indent) if indent else block

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


def week_page_exists(year: int, week: int) -> bool:
    """Check whether an archive page has already been committed for this week."""
    if not config.GITHUB_COMMIT_TOKEN:
        return False
    return _get_file_sha(f"website/uge/{year}/{week}/index.html") is not None


def _fetch_digest_json(year: int, week: int) -> dict | None:
    """Fetch and parse a previously committed week's digest.json, if any."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/website/uge/{year}/{week}/digest.json"
    try:
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        content = base64.b64decode(resp.json()["content"]).decode()
        return json.loads(content)
    except (requests.RequestException, KeyError, ValueError, UnicodeDecodeError):
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


def _render_pager(digest: dict) -> str:
    prev_info = digest.get("prev_week")
    next_info = digest.get("next_week")
    if not prev_info and not next_info:
        return ""

    prev_link = ""
    if prev_info:
        py, pw = prev_info["year"], prev_info["week"]
        prev_link = f'<a class="pager-link pager-prev" href="../../{py}/{pw}/">&larr; Uge {pw}, {py}</a>'

    next_link = ""
    if next_info:
        ny, nw = next_info["year"], next_info["week"]
        next_link = f'<a class="pager-link pager-next" href="../../{ny}/{nw}/">Uge {nw}, {ny} &rarr;</a>'

    return f"""
              <nav class="digest-pager">
                {prev_link}{next_link}
              </nav>
"""


def _render_archive_html(digest: dict) -> str:
    week = digest["week"]
    year = digest["year"]
    total = digest["total_posts"]
    cats = digest["categories"]
    narrative_html = digest.get("narrative_html") or html.escape(digest.get("narrative", ""))
    generated_at = digest.get("generated_at", "")
    notable = digest.get("notable", [])
    category_items = digest.get("category_items", {})
    region_items = digest.get("region_items", {})

    category_accordion_html = _render_accordion(_category_groups(cats, category_items))
    region_accordion_html = _render_accordion(_region_groups(region_items))
    pager_nav = _render_pager(digest)
    signup_section = render_signup_section(" " * 14)

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
          <meta name="description" content="Ugens overblik over politiets opdateringer: {total} meddelelser i uge {week}, {year} — efterlysninger, anholdelser og øvrige sager fra hele Danmark.">
          <link rel="canonical" href="{SITE_BASE_URL}/uge/{year}/{week}/">
          <meta property="og:type" content="article">
          <meta property="og:site_name" content="PolitiUpdate">
          <meta property="og:locale" content="da_DK">
          <meta property="og:title" content="Uge {week}, {year} — PolitiUpdate">
          <meta property="og:description" content="Ugens overblik over politiets opdateringer: {total} meddelelser fra hele Danmark.">
          <meta property="og:url" content="{SITE_BASE_URL}/uge/{year}/{week}/">
          <meta property="og:image" content="{SITE_BASE_URL}/og-image.png">
          <meta property="og:image:width" content="1200">
          <meta property="og:image:height" content="630">
          <meta property="og:image:alt" content="PolitiUpdate — uge {week}, {year}">
          <meta name="twitter:card" content="summary_large_image">
          <meta name="twitter:title" content="Uge {week}, {year} — PolitiUpdate">
          <meta name="twitter:description" content="Ugens overblik over politiets opdateringer: {total} meddelelser fra hele Danmark.">
          <meta name="twitter:image" content="{SITE_BASE_URL}/og-image.png">
          <link rel="icon" href="../../../favicon.svg" type="image/svg+xml">
          <link rel="stylesheet" href="../../../styles.css">
          <link rel="stylesheet" href="../../digest.css">
          <link rel="stylesheet" href="{SIBFORMS_STYLESHEET}">
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
                <p>{narrative_html}</p>
              </article>
{notable_section}{signup_section}
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
{pager_nav}
            </main>

            <footer class="digest-footer">
              <p>Ikke tilknyttet politiet &middot; Data fra <a href="https://via.ritzau.dk" target="_blank" rel="noopener">Ritzau</a></p>
              <p><a href="../../">Seneste uges overblik</a></p>
            </footer>
          </div>
{STATS_TOGGLE_SCRIPT}    <script defer src="{SIBFORMS_SCRIPT}"></script>\
        </body>
        </html>
    """)


def _backfill_next_link(prev_info: dict, year: int, week: int) -> None:
    """After publishing a new week, retroactively point the previous week's
    page forward to it, so pagination works in both directions over time."""
    prev_year, prev_week = prev_info["year"], prev_info["week"]
    prev_digest = _fetch_digest_json(prev_year, prev_week)
    if not prev_digest:
        return

    prev_digest["next_week"] = {"year": year, "week": week}
    base = f"website/uge/{prev_year}/{prev_week}"
    commit_msg = f"feat(digest): link uge {prev_week}/{prev_year} forward to {week}/{year}"
    _put_file(
        f"{base}/digest.json",
        json.dumps(prev_digest, indent=2, ensure_ascii=False),
        commit_msg,
    )
    _put_file(f"{base}/index.html", _render_archive_html(prev_digest), commit_msg)
    logger.info("Backfilled next-week link on %s/%s", prev_week, prev_year)


def _fetch_file_text(path: str) -> str | None:
    """Return a repo file's decoded text via the Contents API, or None."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{path}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return base64.b64decode(resp.json()["content"]).decode()
    except (requests.RequestException, KeyError, ValueError, UnicodeDecodeError):
        return None


def iso_week_lastmod(digest: dict) -> str:
    """The date to advertise as a week page's ``lastmod``.

    The weekly job runs on the Sunday that closes the ISO week, so the digest's
    own ``generated_at`` date is exactly that day (and matches what the hand-
    maintained sitemap used). Fall back to the ISO week's Sunday, and to an
    empty string (a valid sitemap permalink without ``lastmod``) if neither is
    available — a missing date must never block the sitemap update.
    """
    generated_at = digest.get("generated_at") or ""
    if len(generated_at) >= 10 and generated_at[4] == "-" and generated_at[7] == "-":
        return generated_at[:10]
    try:
        return date.fromisocalendar(int(digest["year"]), int(digest["week"]), 7).isoformat()
    except (KeyError, TypeError, ValueError):
        return ""


def _static_blocks() -> list[str]:
    return [
        "  <url>\n"
        f"    <loc>{loc}</loc>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>"
        for loc, changefreq, priority in SITEMAP_STATIC_ENTRIES
    ]


def parse_sitemap(xml_text: str) -> tuple[dict[tuple[int, int], str], list[str]]:
    """Split a sitemap into ``{(year, week): lastmod}`` and the other ``<url>``
    blocks, kept verbatim and in order so a hand-added URL is never dropped."""
    weeks: dict[tuple[int, int], str] = {}
    others: list[str] = []
    for block in _URL_BLOCK_RE.findall(xml_text):
        loc_match = _LOC_RE.search(block)
        if not loc_match:
            continue
        week_match = _WEEK_LOC_RE.search(loc_match.group(1))
        if week_match:
            lastmod_match = _LASTMOD_RE.search(block)
            weeks[(int(week_match.group(1)), int(week_match.group(2)))] = (
                lastmod_match.group(1) if lastmod_match else ""
            )
        elif block.strip() not in [b.strip() for b in others]:
            others.append(block.rstrip())
    return weeks, others


def render_sitemap(
    weeks: dict[tuple[int, int], str], head_blocks: list[str] | None = None
) -> str:
    """Render the sitemap: the landing page and archive index, then every week,
    newest first."""
    blocks = list(head_blocks) if head_blocks else _static_blocks()
    for year, week in sorted(weeks, reverse=True):
        lastmod = weeks[(year, week)]
        lastmod_line = f"\n    <lastmod>{lastmod}</lastmod>" if lastmod else ""
        blocks.append(
            "  <url>\n"
            f"    <loc>{SITE_BASE_URL}/uge/{year}/{week}/</loc>{lastmod_line}\n"
            f"    <changefreq>{WEEK_CHANGEFREQ}</changefreq>\n"
            f"    <priority>{WEEK_PRIORITY}</priority>\n"
            "  </url>"
        )
    return "\n".join(
        ['<?xml version="1.0" encoding="UTF-8"?>', f'<urlset xmlns="{SITEMAP_NS}">', *blocks, "</urlset>"]
    ) + "\n"


def merge_week_into_sitemap(
    xml_text: str | None, digest: dict
) -> tuple[str, dict[tuple[int, int], str], list[str]]:
    """Return ``(sitemap_xml, weeks, head_blocks)`` with this digest's week added.

    Pure: takes the current sitemap text (or None) and the digest, and returns
    the text that should be committed. An existing week keeps its ``lastmod`` so
    re-running a week does not churn the file.
    """
    if xml_text is None:
        weeks: dict[tuple[int, int], str] = {}
        head_blocks: list[str] = _static_blocks()
    else:
        weeks, head_blocks = parse_sitemap(xml_text)
        if not head_blocks:
            head_blocks = _static_blocks()

    key = (int(digest["year"]), int(digest["week"]))
    if not weeks.get(key):
        weeks[key] = iso_week_lastmod(digest)
    return render_sitemap(weeks, head_blocks), weeks, head_blocks


def update_sitemap(digest: dict) -> bool:
    """List this week's archive page in ``website/sitemap.xml`` (commit if changed).

    Returns True when the file was rewritten. Idempotent: a run that would
    produce identical content commits nothing.
    """
    if not config.GITHUB_COMMIT_TOKEN:
        raise RuntimeError(
            "GITHUB_COMMIT_TOKEN is not set. Create a PAT with 'contents: write' scope."
        )

    existing = _fetch_file_text(SITEMAP_PATH)
    content, _weeks, _head = merge_week_into_sitemap(existing, digest)
    if existing is not None and content == existing:
        logger.info("Sitemap already lists week %s/%s", digest["week"], digest["year"])
        return False

    _put_file(
        SITEMAP_PATH,
        content,
        f"feat(digest): list week {digest['week']}/{digest['year']} in sitemap",
    )
    logger.info("Sitemap updated with week %s/%s", digest["week"], digest["year"])
    return True


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

    prev_info = digest.get("prev_week")
    if prev_info:
        try:
            _backfill_next_link(prev_info, year, week)
        except Exception:
            logger.exception("Failed to backfill next-week link on prior page")

    # A published week that is not in the sitemap is a week search engines are
    # never told about, so this is part of publishing, not a follow-up task.
    try:
        update_sitemap(digest)
    except Exception:
        logger.exception("Failed to list week %s/%s in the sitemap", week, year)
