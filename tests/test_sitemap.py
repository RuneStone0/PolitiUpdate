"""The published archive must be discoverable.

Every page a search engine can index on this site is a weekly archive page
(there are no per-release pages), and the sitemap is the only thing that tells
crawlers a new week exists. It was hand-maintained, and it rotted exactly like
every other manual step here: week 37 was published on 2026-09-13 and the live
``sitemap.xml`` still listed only weeks 33–36 four days later — so the newest
week was never announced, while discovery in
``scripts/backfill-archive-pages.py`` reads that same file and therefore also
skipped it.

``publisher.commit_archive`` now rewrites the sitemap as part of publishing the
week. These tests fail if:

  * a published week page exists in the tree but is not listed in
    ``website/sitemap.xml`` (which is what the live site was doing);
  * the sitemap stops being valid sitemap XML, loses its namespace, uses
    relative URLs, or drops the landing page / archive index;
  * the merge logic stops being additive (a hand-added URL would be deleted) or
    stops being idempotent (every digest run would commit a no-op);
  * a sitemap failure is allowed to break the weekly digest run.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import pytest

from src.digest import publisher

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE = REPO_ROOT / "website"
SITEMAP = WEBSITE / "sitemap.xml"

WEEK_PAGE_RE = re.compile(r"^/uge/(\d{4})/(\d{1,2})/$")


def _archive_weeks() -> list[tuple[int, int]]:
    weeks = set()
    for page in WEBSITE.glob("uge/*/*/index.html"):
        try:
            weeks.add((int(page.parent.parent.name), int(page.parent.name)))
        except ValueError:  # pragma: no cover - defensive
            continue
    return sorted(weeks)


def _locs(xml_text: str) -> list[str]:
    return re.findall(r"<loc>\s*([^<]*?)\s*</loc>", xml_text)


def _digest(year: int = 2026, week: int = 37, **extra) -> dict:
    return {"week": week, "year": year, "total_posts": 128, "categories": {}, **extra}


# --- the published file -------------------------------------------------------


def test_sitemap_lists_every_published_week_page() -> None:
    listed = {
        (int(m.group(1)), int(m.group(2)))
        for loc in _locs(SITEMAP.read_text(encoding="utf-8"))
        for m in [WEEK_PAGE_RE.match(loc.replace(publisher.SITE_BASE_URL, ""))]
        if m
    }
    missing = [w for w in _archive_weeks() if w not in listed]
    assert missing == [], (
        f"week page(s) {missing} exist but are not in website/sitemap.xml — "
        "run scripts/backfill-archive-pages.py (a week nobody announces is a week "
        "search engines never index)"
    )


def test_sitemap_is_valid_sitemap_xml() -> None:
    root = ET.fromstring(SITEMAP.read_text(encoding="utf-8"))
    assert root.tag == f"{{{publisher.SITEMAP_NS}}}urlset"


def test_sitemap_has_landing_page_and_archive_index() -> None:
    locs = _locs(SITEMAP.read_text(encoding="utf-8"))
    assert f"{publisher.SITE_BASE_URL}/" in locs
    assert f"{publisher.SITE_BASE_URL}/uge/" in locs


def test_sitemap_urls_are_absolute() -> None:
    bad = [loc for loc in _locs(SITEMAP.read_text(encoding="utf-8"))
           if not loc.startswith(f"{publisher.SITE_BASE_URL}/")]
    assert bad == [], f"crawlers need absolute URLs, found {bad}"


def test_rerendering_the_published_sitemap_changes_nothing() -> None:
    """The digest run rewrites this file every week — it must not churn it."""
    existing = SITEMAP.read_text(encoding="utf-8")
    weeks, others = publisher.parse_sitemap(existing)
    assert publisher.render_sitemap(weeks, others) == existing


# --- rendering ---------------------------------------------------------------


def test_render_lists_weeks_newest_first_with_lastmod() -> None:
    xml_text = publisher.render_sitemap({(2026, 33): "2026-08-16", (2026, 37): "2026-09-13"})
    week_locs = [loc for loc in _locs(xml_text) if WEEK_PAGE_RE.match(loc.replace(publisher.SITE_BASE_URL, ""))]
    assert week_locs == [
        f"{publisher.SITE_BASE_URL}/uge/2026/37/",
        f"{publisher.SITE_BASE_URL}/uge/2026/33/",
    ]
    assert "<lastmod>2026-09-13</lastmod>" in xml_text


def test_render_omits_lastmod_when_unknown() -> None:
    xml_text = publisher.render_sitemap({(2026, 37): ""})
    assert "<lastmod>" not in xml_text
    ET.fromstring(xml_text)  # still valid


def test_parse_keeps_other_urls_verbatim_and_in_order() -> None:
    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="{publisher.SITEMAP_NS}">\n'
        "  <url>\n    <loc>https://example.test/feedback/</loc>\n  </url>\n"
        "  <url>\n    <loc>https://example.test/uge/2026/36/</loc>\n"
        "    <lastmod>2026-09-06</lastmod>\n  </url>\n"
        "</urlset>\n"
    )
    weeks, others = publisher.parse_sitemap(xml_text)
    assert weeks == {(2026, 36): "2026-09-06"}
    assert len(others) == 1 and "example.test/feedback/" in others[0]

    rendered = publisher.render_sitemap(weeks, others)
    assert "example.test/feedback/" in rendered  # additive merge, nothing dropped


# --- lastmod -----------------------------------------------------------------


def test_lastmod_uses_generated_at_date() -> None:
    assert publisher.iso_week_lastmod(_digest(generated_at="2026-09-13T16:00:18+00:00")) == "2026-09-13"


def test_lastmod_falls_back_to_the_iso_week_sunday() -> None:
    assert publisher.iso_week_lastmod(_digest(year=2026, week=37)) == "2026-09-13"
    assert publisher.iso_week_lastmod(_digest(generated_at="garbage")) == "2026-09-13"


def test_lastmod_is_empty_when_nothing_is_known() -> None:
    assert publisher.iso_week_lastmod({"week": 99, "year": 2026, "generated_at": ""}) == ""
    assert publisher.iso_week_lastmod({}) == ""


# --- merging -----------------------------------------------------------------


def test_merge_adds_the_new_week_to_an_existing_sitemap() -> None:
    existing = publisher.render_sitemap({(2026, 36): "2026-09-06"})
    content, weeks, _head = publisher.merge_week_into_sitemap(existing, _digest())
    assert weeks == {(2026, 36): "2026-09-06", (2026, 37): "2026-09-13"}
    assert f"{publisher.SITE_BASE_URL}/uge/2026/37/" in content
    assert f"{publisher.SITE_BASE_URL}/uge/2026/36/" in content


def test_merge_keeps_an_existing_lastmod() -> None:
    existing = publisher.render_sitemap({(2026, 37): "2026-09-01"})
    content, weeks, _head = publisher.merge_week_into_sitemap(existing, _digest())
    assert weeks[(2026, 37)] == "2026-09-01"
    assert "<lastmod>2026-09-01</lastmod>" in content


def test_merge_builds_a_sitemap_from_nothing() -> None:
    content, weeks, _head = publisher.merge_week_into_sitemap(None, _digest())
    assert weeks == {(2026, 37): "2026-09-13"}
    locs = _locs(content)
    assert locs[0] == f"{publisher.SITE_BASE_URL}/"
    assert locs[1] == f"{publisher.SITE_BASE_URL}/uge/"
    ET.fromstring(content)


# --- committing ---------------------------------------------------------------


def test_update_sitemap_commits_the_new_week(monkeypatch) -> None:
    existing = publisher.render_sitemap({(2026, 36): "2026-09-06"})
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    monkeypatch.setattr(publisher, "_fetch_file_text", lambda path: existing)
    with mock.patch.object(publisher, "_put_file") as put:
        assert publisher.update_sitemap(_digest()) is True
    path, content, message = put.call_args.args
    assert path == "website/sitemap.xml"
    assert f"{publisher.SITE_BASE_URL}/uge/2026/37/" in content
    assert "37" in message


def test_update_sitemap_is_idempotent(monkeypatch) -> None:
    existing, _weeks, _head = publisher.merge_week_into_sitemap(None, _digest())
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    monkeypatch.setattr(publisher, "_fetch_file_text", lambda path: existing)
    with mock.patch.object(publisher, "_put_file") as put:
        assert publisher.update_sitemap(_digest()) is False
    put.assert_not_called()


def test_update_sitemap_requires_a_token(monkeypatch) -> None:
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "")
    with pytest.raises(RuntimeError):
        publisher.update_sitemap(_digest())


def test_commit_archive_lists_the_week_in_the_sitemap(monkeypatch) -> None:
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    with mock.patch.object(publisher, "_put_file") as put:
        with mock.patch.object(publisher, "update_sitemap") as update:
            publisher.commit_archive(_digest())
    update.assert_called_once()
    assert put.call_count == 2  # digest.json + index.html


def test_a_sitemap_failure_never_breaks_the_digest_run(monkeypatch) -> None:
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    with mock.patch.object(publisher, "_put_file") as put:
        with mock.patch.object(publisher, "update_sitemap", side_effect=RuntimeError("boom")):
            publisher.commit_archive(_digest())  # must not raise
    assert put.call_count == 2
