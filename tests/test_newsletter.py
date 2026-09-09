"""Tests for the newsletter builder's region grouping.

Covers the key subtlety of the newsletter spec: nationwide releases are
auto-included into *every* region's briefing, not just a "national" group.
"""

import sqlite3
from datetime import timedelta

import pytest

from src.common import regions as region_map
from src.newsletter import builder
from src.newsletter import config as nconfig


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE posts (
            guid TEXT PRIMARY KEY, title TEXT, body TEXT,
            posted_at TEXT, status TEXT, x_post_id TEXT,
            pub_date TEXT, district TEXT
        )
        """
    )
    for r in rows:
        conn.execute(
            "INSERT INTO posts (guid,title,body,posted_at,status,x_post_id,pub_date,district)"
            " VALUES (?,?,?,?,?,?,?,?)",
            r,
        )
    conn.commit()
    conn.close()


def _row(guid, title, district, post_time):
    return (guid, title, f"Body for {title}", post_time, "posted", "x-" + guid, "2026-08-01", district)


def _time_near_week_start(year=2026, week=36):
    return (builder._iso_week_start(year, week) + timedelta(hours=12)).isoformat()


@pytest.fixture
def seed_db(tmp_path, monkeypatch):
    path = str(tmp_path / "nl.db")
    monkeypatch.setattr(nconfig, "DB_PATH", path)
    return path


def test_national_autoincluded_in_every_region(seed_db):
    t = _time_near_week_start()
    _make_db(
        seed_db,
        [
            _row("k1", "København opdatering", "Københavns Politi", t),
            _row("F1", "Fyn opdatering", "Fyns Politi", t),
            _row("n1", "National opdatering", "Rigspolitiet", t),
            _row("n2", "NSK opdatering", "National enhed for Særlig Kriminalitet", t),
        ],
    )

    data = builder.build(2026, 36)

    assert data["total_posts"] == 4
    assert data["totals"] == {"regional": 2, "national": 2}
    assert len(data["national"]) == 2

    # A region with its own post gets it PLUS every national release.
    hoved = data["regions"][region_map.REGION_HOVEDSTADEN]
    assert any(p["title"] == "København opdatering" for p in hoved)
    assert any(p["title"] == "National opdatering" for p in hoved)
    assert any(p["title"] == "NSK opdatering" for p in hoved)

    # A region with no local posts still gets the national releases.
    jylland = data["regions"][region_map.REGION_JYLLAND]
    assert all(p["title"].startswith(("National", "NSK")) for p in jylland)
    assert len(jylland) == 2


def test_unknown_district_bucketed_separately(seed_db):
    t = _time_near_week_start()
    _make_db(
        seed_db,
        [
            _row("k1", "København opdatering", "Københavns Politi", t),
            _row("u1", "Ukendt opdatering", "Et helt ukendt distrikt", t),
        ],
    )

    data = builder.build(2026, 36)

    assert data["total_posts"] == 2
    assert len(data["unknown"]) == 1
    assert len(data["national"]) == 0
    # Unknown posts are NOT injected into regions.
    assert len(data["regions"][region_map.REGION_HOVEDSTADEN]) == 1
