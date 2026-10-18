"""Commit the weekly archive pages to the repo via the GitHub API.

Publishes, in a SINGLE commit (Git Data API — see ``_commit_files``):
  website/uge/{year}/{week}/index.html   — static archive page
  website/uge/{year}/{week}/digest.json  — baked-in data (no runtime fetch)
  website/uge/{prev}/…                   — forward link on the previous week
  website/sitemap.xml                    — keeps this week discoverable

One commit means one push, one CI run and one Pages deploy — and no
intermediate commit in which a published week page is missing from the sitemap
(that used to make every digest run push 3 red builds).
Requires a PAT with 'contents: write' scope (GITHUB_COMMIT_TOKEN env var).
"""

import base64
import html
import json
import logging
import os
import re
import textwrap
from datetime import date, timedelta

import requests

from . import config
from src.newsletter import cases as case_identity

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


def _commit_files(files: dict, message: str, branch: str = "main") -> str:
    """Commit several files as ONE commit, via the Git Data API.

    A week's publish touches up to five files (the page, its data, the previous
    week's forward link, the sitemap, the archive index). The Contents API can
    only write one file per commit, so publishing them one by one produced a
    chain of intermediate commits that each pushed to `main` and each ran the
    full Test workflow — and every commit except the last was RED by
    construction, because it added a week page the sitemap did not list yet
    (`tests/test_sitemap.py::test_sitemap_lists_every_published_week_page`).

    Measured 2026-10-18: one digest run = 5 pushes = 3 failed Test runs
    (`unit` + `docker`, both running the same sitemap test) and the same every
    Sunday since the sitemap gate landed. The publish is atomic here instead:
    one commit, one push, one CI run, and no window in which a week page is
    published but unindexed.

    Returns the new commit SHA. Retries once when `main` moved between reading
    the head and updating the ref (a non-fast-forward update is rejected).
    """
    if not files:
        return ""

    repo = f"{GITHUB_API}/repos/{config.GITHUB_REPO}"
    headers = _headers()
    last_error: Exception | None = None

    for attempt in (1, 2):
        try:
            ref = requests.get(f"{repo}/git/ref/heads/{branch}", headers=headers, timeout=30)
            ref.raise_for_status()
            head_sha = ref.json()["object"]["sha"]

            head = requests.get(f"{repo}/git/commits/{head_sha}", headers=headers, timeout=30)
            head.raise_for_status()
            base_tree = head.json()["tree"]["sha"]

            tree = requests.post(
                f"{repo}/git/trees",
                headers=headers,
                json={
                    "base_tree": base_tree,
                    "tree": [
                        {"path": path, "mode": "100644", "type": "blob", "content": content}
                        for path, content in files.items()
                    ],
                },
                timeout=60,
            )
            tree.raise_for_status()

            commit = requests.post(
                f"{repo}/git/commits",
                headers=headers,
                json={
                    "message": message,
                    "tree": tree.json()["sha"],
                    "parents": [head_sha],
                },
                timeout=30,
            )
            commit.raise_for_status()
            new_sha = commit.json()["sha"]

            update = requests.patch(
                f"{repo}/git/refs/heads/{branch}",
                headers=headers,
                json={"sha": new_sha, "force": False},
                timeout=30,
            )
            if update.status_code in (409, 422) and attempt == 1:
                logger.warning("%s moved while publishing — retrying", branch)
                continue
            update.raise_for_status()
        except requests.RequestException as exc:
            last_error = exc
            raise
        for path in files:
            logger.info("Committed %s", path)
        logger.info(
            "Single commit %s on %s carries %d file(s)", new_sha[:8], branch, len(files)
        )
        return new_sha

    raise last_error if last_error else RuntimeError(f"Could not update {branch}")


DANISH_MONTHS = (
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
)


def week_range_label(year: int, week: int) -> str:
    """``"21.–27. september 2026"`` — the span a reader can place, not an ISO week.

    "Uge 39, 2026" is exact and useless: nobody knows which days that covers. The
    mail has said "21.–27. september 2026" all along; the page now agrees.
    """
    try:
        monday = date.fromisocalendar(year, week, 1)
    except ValueError:  # pragma: no cover - a bad week number should not 500 the page
        return ""
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.day}.–{sunday.day}. {DANISH_MONTHS[monday.month - 1]} {sunday.year}"
    # A week can straddle the new year (week 53 of 2026 ends 3 January 2027), so
    # the year is printed with the day it belongs to rather than once at the end.
    monday_year = f" {monday.year}" if monday.year != sunday.year else ""
    return (
        f"{monday.day}. {DANISH_MONTHS[monday.month - 1]}{monday_year} – "
        f"{sunday.day}. {DANISH_MONTHS[sunday.month - 1]} {sunday.year}"
    )


def _render_cat_items(items: list[dict]) -> str:
    """One row per case, not per update, and quiet about it.

    The list used to print every posted update, so "Eftersøgning af 91-årig kvinde
    i Randers" appeared three times in one category and the same case reappeared
    under its region — 93 rows for 61 cases. Rows now collapse on the case key the
    digest bakes in (``case``), falling back to a normalised headline for weeks
    published before that field existed, and the newest word for the case is the
    one shown while ``N opdateringer`` says how many updates it took to get there.
    Links stay dark like the briefing's index: colour is reserved for the
    most-read block, so a 20-row list does not light up blue.
    """
    rows = []
    for item in _case_rows(items):
        title = html.escape(item["title"])
        meta = (
            f'<span class="row-meta">{item["updates"]} opdateringer</span>'
            if item["updates"] > 1
            else ""
        )
        arrow = '<span class="row-arrow" aria-hidden="true">→</span>'
        if item.get("url"):
            rows.append(
                f'<li><a class="case-row" href="{html.escape(item["url"])}" '
                f'target="_blank" rel="noopener"><span class="case-row-title">{title}</span>'
                f"{meta}{arrow}</a></li>"
            )
        else:
            rows.append(
                f'<li><span class="case-row case-row-plain">'
                f'<span class="case-row-title">{title}</span>{meta}</span></li>'
            )
    return "\n".join(rows)


def _case_rows(items: list[dict]) -> list[dict]:
    """Collapse rows that describe the same case (see ``_render_cat_items``)."""
    groups: dict[str, list[dict]] = {}
    for item in items:
        key = item.get("case") or case_identity.title_key(item)
        groups.setdefault(key, []).append(item)

    rows = []
    for members in groups.values():
        lead = next((m for m in members if m.get("primary")), None) or members[-1]
        # Weeks published before `updates` existed still tell the truth: the number
        # of rows we just merged is itself a lower bound on the updates.
        updates = max(len(members), max(int(m.get("updates") or 1) for m in members))
        rows.append({"title": lead["title"], "url": lead.get("url"), "updates": updates})
    return rows


def _render_accordion(groups: list[tuple[str, list[dict]]]) -> str:
    """groups: [(label, items)] in the order they should appear, already
    filtered to non-empty groups. The badge counts *cases*; when a group holds
    more updates than cases the update count is spelled out next to it so nothing
    about the week is hidden by the collapsing."""
    blocks = []
    for label, items in groups:
        rows = _case_rows(items)
        items_html = _render_cat_items(items)
        updates_note = (
            f'<span class="cat-meta">{len(items)} opdateringer</span>'
            if len(items) != len(rows)
            else ""
        )
        blocks.append(
            f'<details class="cat-item">\n'
            f'  <summary><span class="cat-count">{len(rows)}</span>'
            f'<span class="cat-label">{html.escape(label)}</span>{updates_note}</summary>\n'
            f'  <ul class="cat-item-list">\n    {items_html}\n  </ul>\n'
            f"</details>"
        )
    return "\n".join(blocks)


def _render_highlights(digest: dict) -> str:
    """The page's lead: the cases most read on X, same five the mail leads with.

    Rendered only when the digest carries reach data — without view counts
    "mest læste" would be an invention, so the section is dropped instead.
    """
    highlights = digest.get("highlights") or []
    cards = []
    for rank, item in enumerate(highlights, start=1):
        url = html.escape(item.get("url") or "")
        if not url:
            continue
        updates = (
            f'<span class="highlight-updates">{item["updates"]} opdateringer i sagen</span>'
            if int(item.get("updates") or 1) > 1
            else ""
        )
        cards.append(
            f'<li class="highlight-card">\n'
            f'  <span class="highlight-rank">{rank}</span>\n'
            f'  <div class="highlight-body">\n'
            f'    <h3><a href="{url}" target="_blank" rel="noopener">'
            f'{html.escape(item["title"])}</a></h3>\n'
            f'    <p class="highlight-summary">{html.escape(item.get("summary") or "")}</p>\n'
            f'    <p class="highlight-link"><a href="{url}" target="_blank" rel="noopener">'
            f"Læs hele opslaget på X &rarr;</a>{updates}</p>\n"
            f"  </div>\n"
            f"</li>"
        )
    if not cards:
        return ""

    return (
        '              <section class="digest-highlights">\n'
        "                <h2>Ugens mest læste sager</h2>\n"
        '                <p class="highlights-note">De sager flest læste på X i uge '
        f'{html.escape(str(digest.get("week", "")))}</p>\n'
        '                <ol class="highlight-list">\n                  '
        + "\n                  ".join(cards)
        + "\n                </ol>\n"
        "              </section>\n"
    )


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

    case_count = digest.get("case_count") or 0
    highlights_section = _render_highlights(digest)
    range_label = week_range_label(year, week)
    meta_parts = [part for part in (range_label, f"{total} opdateringer") if part]
    if case_count:
        meta_parts.append(f"{case_count} sager")
    meta_line = " · ".join(meta_parts)
    breakdown_note = (
        f"{total} opdateringer i {case_count} sager — en sag med flere opdateringer "
        "står som én linje."
        if case_count
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
          <meta name="description" content="Ugens overblik over politiets opdateringer: {meta_line} — efterlysninger, anholdelser og øvrige sager fra hele Danmark.">
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
              <p class="digest-meta">{meta_line}</p>
            </header>

            <main class="digest-main">
{highlights_section}              <article class="digest-narrative">
                <h2>Ugens gang</h2>
                <p>{narrative_html}</p>
              </article>
{notable_section}{signup_section}
              <section class="digest-breakdown" id="stats-section">
                <div class="stats-header">
                  <h2>Alle ugens sager</h2>
                  <div class="sort-toggle" role="group" aria-label="Sortér efter">
                    <button type="button" class="sort-btn active" data-sort="category">Kategori</button>
                    <button type="button" class="sort-btn" data-sort="region">Region</button>
                  </div>
                </div>
                <p class="breakdown-note">{breakdown_note}</p>
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


def _next_link_files(prev_info: dict, year: int, week: int) -> dict:
    """Files needed to point the previous week's page forward to this one.

    Empty when there is no previous digest to link from (or it cannot be read),
    so the caller's atomic commit simply carries fewer files.
    """
    prev_year, prev_week = prev_info["year"], prev_info["week"]
    prev_digest = _fetch_digest_json(prev_year, prev_week)
    if not prev_digest:
        return {}

    prev_digest["next_week"] = {"year": year, "week": week}
    base = f"website/uge/{prev_year}/{prev_week}"
    return {
        f"{base}/digest.json": json.dumps(prev_digest, indent=2, ensure_ascii=False),
        f"{base}/index.html": _render_archive_html(prev_digest),
    }


def _backfill_next_link(prev_info: dict, year: int, week: int) -> None:
    """After publishing a new week, retroactively point the previous week's
    page forward to it, so pagination works in both directions over time."""
    files = _next_link_files(prev_info, year, week)
    if not files:
        return
    commit_msg = f"feat(digest): link uge {prev_info['week']}/{prev_info['year']} forward to {week}/{year}"
    for path, content in files.items():
        _put_file(path, content, commit_msg)
    logger.info("Backfilled next-week link on %s/%s", prev_info["week"], prev_info["year"])


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


def _sitemap_files(digest: dict) -> dict:
    """The sitemap rewrite this week needs, or ``{}`` when it is already listed."""
    existing = _fetch_file_text(SITEMAP_PATH)
    content, _weeks, _head = merge_week_into_sitemap(existing, digest)
    if existing is not None and content == existing:
        logger.info("Sitemap already lists week %s/%s", digest["week"], digest["year"])
        return {}
    return {SITEMAP_PATH: content}


def update_sitemap(digest: dict) -> bool:
    """List this week's archive page in ``website/sitemap.xml`` (commit if changed).

    Returns True when the file was rewritten. Idempotent: a run that would
    produce identical content commits nothing.
    """
    if not config.GITHUB_COMMIT_TOKEN:
        raise RuntimeError(
            "GITHUB_COMMIT_TOKEN is not set. Create a PAT with 'contents: write' scope."
        )

    files = _sitemap_files(digest)
    if not files:
        return False

    _put_file(
        SITEMAP_PATH,
        files[SITEMAP_PATH],
        f"feat(digest): list week {digest['week']}/{digest['year']} in sitemap",
    )
    logger.info("Sitemap updated with week %s/%s", digest["week"], digest["year"])
    return True


def commit_archive(digest: dict) -> str:
    """Publish a week's archive — page, data, forward link, sitemap — in ONE commit.

    Every file a week needs is assembled first and committed atomically, so
    `main` never carries a published week page that the sitemap does not list
    (which is what made 3 of every 4 digest pushes fail CI: each intermediate
    commit pushed on its own and ran the sitemap gate against an incomplete
    tree). Returns the commit SHA (empty when there was nothing to write).
    """
    if not config.GITHUB_COMMIT_TOKEN:
        raise RuntimeError(
            "GITHUB_COMMIT_TOKEN is not set. Create a PAT with 'contents: write' scope."
        )

    week = digest["week"]
    year = digest["year"]
    base = f"website/uge/{year}/{week}"
    commit_msg = f"feat(digest): add week {week}/{year} archive"

    digest_without_posts = {k: v for k, v in digest.items() if k != "posts_by_category"}
    files = {
        f"{base}/digest.json": json.dumps(
            digest_without_posts, indent=2, ensure_ascii=False
        ),
        f"{base}/index.html": _render_archive_html(digest),
    }
    details: list[str] = []

    prev_info = digest.get("prev_week")
    if prev_info:
        try:
            previous = _next_link_files(prev_info, year, week)
        except Exception:
            logger.exception("Failed to backfill next-week link on prior page")
            previous = {}
        if previous:
            files.update(previous)
            details.append(
                f"link uge {prev_info['week']}/{prev_info['year']} forward to {week}/{year}"
            )

    # A published week that is not in the sitemap is a week search engines are
    # never told about, so this is part of publishing, not a follow-up task.
    try:
        sitemap = _sitemap_files(digest)
    except Exception:
        logger.exception("Failed to list week %s/%s in the sitemap", week, year)
        sitemap = {}
    if sitemap:
        files.update(sitemap)
        details.append(f"list week {week}/{year} in sitemap")

    if details:
        commit_msg += "\n\n" + "\n".join(f"- {detail}" for detail in details)

    sha = _commit_files(files, commit_msg)
    logger.info("Archive for week %s/%s committed to repo in one commit", week, year)
    return sha
