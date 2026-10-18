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


def test_commit_archive_publishes_the_week_and_the_sitemap_in_one_commit(monkeypatch) -> None:
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    existing = publisher.render_sitemap({(2026, 36): "2026-09-06"})
    monkeypatch.setattr(publisher, "_fetch_file_text", lambda path: existing)
    with mock.patch.object(publisher, "_commit_files") as commit:
        publisher.commit_archive(_digest())
    assert commit.call_count == 1, "one push, one CI run"
    files, message = commit.call_args.args
    assert set(files) == {
        "website/uge/2026/37/digest.json",
        "website/uge/2026/37/index.html",
        "website/sitemap.xml",
    }
    assert f"{publisher.SITE_BASE_URL}/uge/2026/37/" in files["website/sitemap.xml"]
    assert "37" in message


def test_commit_archive_never_pushes_a_week_the_sitemap_does_not_list(monkeypatch) -> None:
    """The red-CI cause: an intermediate commit with the page but not the sitemap.

    The two must travel together, because the CI gate
    (``test_sitemap_lists_every_published_week_page``) runs on every push.
    """
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    monkeypatch.setattr(publisher, "_fetch_file_text", lambda path: None)
    with mock.patch.object(publisher, "_commit_files") as commit:
        publisher.commit_archive(_digest())
    files = commit.call_args.args[0]
    page = "website/uge/2026/37/index.html"
    if page in files:
        assert "website/sitemap.xml" in files


def test_commit_archive_carries_the_previous_week_forward_link(monkeypatch) -> None:
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    monkeypatch.setattr(publisher, "_fetch_file_text", lambda path: None)
    monkeypatch.setattr(
        publisher,
        "_fetch_digest_json",
        lambda year, week: {"week": week, "year": year, "total_posts": 10, "categories": {}},
    )
    with mock.patch.object(publisher, "_commit_files") as commit:
        publisher.commit_archive(_digest(prev_week={"year": 2026, "week": 36}))
    files = commit.call_args.args[0]
    assert "website/uge/2026/36/index.html" in files
    assert "website/uge/2026/36/digest.json" in files
    assert "link uge 36/2026 forward to 37/2026" in commit.call_args.args[1]


def test_a_sitemap_failure_never_breaks_the_digest_run(monkeypatch) -> None:
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    with mock.patch.object(publisher, "_commit_files") as commit:
        with mock.patch.object(publisher, "_sitemap_files", side_effect=RuntimeError("boom")):
            publisher.commit_archive(_digest())  # must not raise
    files = commit.call_args.args[0]
    assert "website/uge/2026/37/index.html" in files
    assert "website/sitemap.xml" not in files


def test_commit_files_writes_every_file_in_one_commit(monkeypatch) -> None:
    """The Git Data API mechanics: one tree, one commit, one ref update."""
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json") or {}))
        resp = mock.Mock(status_code=200)
        if url.endswith("/git/ref/heads/main"):
            resp.json.return_value = {"object": {"sha": "head123"}}
        elif url.endswith("/git/commits/head123"):
            resp.json.return_value = {"tree": {"sha": "treebase"}}
        elif url.endswith("/git/trees"):
            resp.json.return_value = {"sha": "treenew"}
        elif url.endswith("/git/commits"):
            resp.json.return_value = {"sha": "commitnew"}
        else:
            resp.json.return_value = {}
        resp.raise_for_status.return_value = None
        return resp

    with mock.patch.object(publisher.requests, "get", lambda url, **kw: fake_request("GET", url, **kw)), \
         mock.patch.object(publisher.requests, "post", lambda url, **kw: fake_request("POST", url, **kw)), \
         mock.patch.object(publisher.requests, "patch", lambda url, **kw: fake_request("PATCH", url, **kw)):
        sha = publisher._commit_files({"a.txt": "A", "b/c.txt": "C"}, "msg")

    assert sha == "commitnew"
    methods = [m for m, _u, _j in calls]
    assert methods == ["GET", "GET", "POST", "POST", "PATCH"]
    tree_body = [j for m, u, j in calls if u.endswith("/git/trees")][0]
    assert tree_body["base_tree"] == "treebase"
    assert [entry["path"] for entry in tree_body["tree"]] == ["a.txt", "b/c.txt"]
    assert [entry["content"] for entry in tree_body["tree"]] == ["A", "C"]
    commit_body = [j for m, u, j in calls if u.endswith("/git/commits")][0]
    assert commit_body["parents"] == ["head123"]
    assert commit_body["tree"] == "treenew"
    ref_body = [j for m, u, j in calls if u.endswith("/git/refs/heads/main")][0]
    assert ref_body == {"sha": "commitnew", "force": False}


def test_commit_files_retries_when_main_moved(monkeypatch) -> None:
    monkeypatch.setattr(publisher.config, "GITHUB_COMMIT_TOKEN", "fake-token")
    patches = {"n": 0}

    def fake_request(method, url, **kwargs):
        resp = mock.Mock(status_code=200)
        if url.endswith("/git/ref/heads/main"):
            resp.json.return_value = {"object": {"sha": "head123"}}
        elif url.endswith("/git/commits/head123"):
            resp.json.return_value = {"tree": {"sha": "treebase"}}
        elif url.endswith("/git/trees"):
            resp.json.return_value = {"sha": "treenew"}
        elif url.endswith("/git/commits"):
            resp.json.return_value = {"sha": "commitnew"}
        elif url.endswith("/git/refs/heads/main"):
            patches["n"] += 1
            resp.status_code = 422 if patches["n"] == 1 else 200
            resp.json.return_value = {}
        resp.raise_for_status.return_value = None
        return resp

    with mock.patch.object(publisher.requests, "get", lambda url, **kw: fake_request("GET", url, **kw)), \
         mock.patch.object(publisher.requests, "post", lambda url, **kw: fake_request("POST", url, **kw)), \
         mock.patch.object(publisher.requests, "patch", lambda url, **kw: fake_request("PATCH", url, **kw)):
        assert publisher._commit_files({"a.txt": "A"}, "msg") == "commitnew"

    assert patches["n"] == 2, "a rejected non-fast-forward update must be retried once"


def test_commit_files_with_nothing_to_write_does_nothing() -> None:
    assert publisher._commit_files({}, "msg") == ""
