"""Tests for the public X view-count lookup (``src/common/x_reach``).

Reach is ranking data for the briefing, so the bar is: parse defensively, never
raise, and never turn a missing number into 0 (which would read as "nobody saw
this").
"""

import pytest

from src.common import x_reach


def test_parse_reach_reads_the_view_count():
    assert x_reach.parse_reach({"tweet": {"views": 172}}) == 172
    assert x_reach.parse_reach({"tweet": {"views": 0}}) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"tweet": None},
        {"tweet": {}},
        {"tweet": {"views": None}},
        {"tweet": {"views": "172"}},
        {"tweet": {"views": -3}},
        {"tweet": {"views": True}},
        {"code": 404, "message": "NOT_FOUND", "tweet": None},
    ],
)
def test_parse_reach_returns_none_for_anything_unexpected(payload):
    """A missing/odd value is "unknown", never 0 — 0 would rank as unread."""
    assert x_reach.parse_reach(payload) is None


def test_post_id_from_status_url():
    assert x_reach.post_id_from_status_url("https://x.com/PolitiUpdate/status/2100462561758175337") == (
        "2100462561758175337"
    )
    assert x_reach.post_id_from_status_url("https://twitter.com/PolitiUpdate/status/123/") == "123"
    assert x_reach.post_id_from_status_url("https://api.fxtwitter.com/PolitiUpdate/status/456") == "456"
    # an ordinary URL that merely ends in digits is not a post id
    assert x_reach.post_id_from_status_url("https://politiupdates.dk/uge/2026/38/") is None
    assert x_reach.post_id_from_status_url("https://x.com/PolitiUpdate") is None
    assert x_reach.post_id_from_status_url("") is None


def test_fetch_views_returns_only_the_ids_it_could_read(monkeypatch):
    monkeypatch.setattr(x_reach, "_fetch_one", lambda post_id, timeout: {"1": 10, "2": 20}.get(post_id))
    views = x_reach.fetch_views(["1", "2", "3", None])
    assert views == {"1": 10, "2": 20}


def test_fetch_views_is_empty_without_ids():
    assert x_reach.fetch_views([]) == {}
    assert x_reach.fetch_views([None, ""]) == {}


def test_fetch_views_never_raises_when_a_lookup_explodes(monkeypatch):
    def boom(post_id, timeout):
        raise ValueError("unexpected")

    monkeypatch.setattr(x_reach, "_fetch_one", boom)
    assert x_reach.fetch_views(["1", "2"]) == {}


def test_fetch_views_caps_the_work(monkeypatch):
    seen = []

    def record(post_id, timeout):
        seen.append(post_id)
        return 5

    monkeypatch.setattr(x_reach, "_fetch_one", record)
    views = x_reach.fetch_views([str(n) for n in range(10)], max_posts=3)
    assert len(seen) == 3
    assert views == {"0": 5, "1": 5, "2": 5}
