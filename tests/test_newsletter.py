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
from src.newsletter import generator, sender


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


# --- Brevo campaign send (region lists + unsubscribe) ------------------------


def test_region_list_mapping_covers_every_region():
    for label in [*region_map.REGIONS, region_map.REGION_NATIONAL]:
        assert sender.list_id_for_region(label), f"no Brevo list mapped for {label!r}"
    assert sender.list_id_for_region("Findes ikke") is None


def test_campaign_payload_shape(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_SENDER_EMAIL", "nyhedsbrev@mail.politiupdate.com")
    monkeypatch.setattr(nconfig, "BREVO_SENDER_NAME", "PolitiUpdate")
    monkeypatch.setattr(nconfig, "BREVO_UNSUB_PAGE_ID", "")
    payload = sender.campaign_payload(
        region_map.REGION_JYLLAND, "Emne", "<p>Hej</p>", 5, name="Navn"
    )
    assert payload["name"] == "Navn"
    assert payload["subject"] == "Emne"
    assert payload["htmlContent"] == "<p>Hej</p>"
    assert payload["recipients"] == {"listIds": [5]}
    assert payload["sender"] == {"name": "PolitiUpdate", "email": "nyhedsbrev@mail.politiupdate.com"}
    assert "unsubscriptionPageId" not in payload


def test_campaign_payload_attaches_custom_unsub_page(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_UNSUB_PAGE_ID", "abc123def456")
    payload = sender.campaign_payload(region_map.REGION_FYN, "S", "<p>x</p>", 6)
    assert payload["unsubscriptionPageId"] == "abc123def456"


def test_send_region_campaign_dry_run_never_touches_network(monkeypatch):
    def boom(*_a, **_k):  # any HTTP call fails the test
        raise AssertionError("network call made during dry-run")

    monkeypatch.setattr(sender.requests, "post", boom)
    res = sender.send_region_campaign(region_map.REGION_JYLLAND, "S", "<p>x</p>", dry_run=True)
    assert res["dry_run"] is True
    assert res["list_id"] == 5
    assert res["sent"] is False


def test_generate_html_has_title_link_and_region():
    posts = [
        {
            "title": "Efterlysning",
            "district": "Fyns Politi",
            "body": "Første linje\nAnden linje",
            "x_post_id": "123",
        }
    ]
    brief = generator.generate(region_map.REGION_FYN, posts, 36, 2026)
    assert brief["subject"]
    assert "Efterlysning" in brief["html"]
    assert "https://x.com/PolitiUpdate/status/123" in brief["html"]
    assert "Fyn" in brief["html"]
    assert "Efterlysning" in brief["text"]


# --- Default audience: no subscriber state may end up with no briefing -------
#
# Regression guard for a funnel that collected signups and delivered nothing:
# the live Brevo form captures e-mail only, so every real contact has an empty
# REGION attribute, matched no region list, and would have received no briefing
# at all. Whatever the attribute value, a subscriber must land on exactly one
# briefing — the country-wide one when nothing else matches.


def test_routing_maps_every_subscriber_state_to_a_briefing():
    from src.newsletter import routing

    assert routing.briefing_region("Jylland") == region_map.REGION_JYLLAND
    assert routing.briefing_region("  Hovedstaden  ") == region_map.REGION_HOVEDSTADEN
    for value in ("", None, "   ", "Nordpolen", "Hele landet"):
        assert routing.briefing_region(value) == region_map.REGION_NATIONAL


def test_send_order_puts_the_country_wide_briefing_last():
    from src.newsletter import routing

    assert routing.send_order() == [*region_map.REGIONS, region_map.REGION_NATIONAL]


def test_builder_exposes_every_release_for_the_country_wide_briefing(seed_db):
    t = _time_near_week_start()
    _make_db(
        seed_db,
        [
            _row("k1", "København opdatering", "Københavns Politi", t),
            _row("n1", "National opdatering", "Rigspolitiet", t),
            _row("u1", "Ukendt opdatering", "Et helt ukendt distrikt", t),
        ],
    )

    data = builder.build(2026, 36)

    assert data["total_posts"] == 3
    assert len(data["everything"]) == 3
    assert {p["title"] for p in data["everything"]} == {
        "København opdatering",
        "National opdatering",
        "Ukendt opdatering",
    }
    # It is a briefing of its own, not one of the four regional buckets.
    assert region_map.REGION_NATIONAL not in data["regions"]


def test_country_wide_heading_reads_plainly():
    posts = [{"title": "T", "district": "Rigspolitiet", "body": "B", "x_post_id": "1"}]
    brief = generator.generate(region_map.REGION_NATIONAL, posts, 36, 2026)
    assert "PolitiUpdate — ugens overblik fra hele landet" in brief["text"]
    assert "for Hele landet" not in brief["text"]
    assert "for Hele landet" not in brief["html"]


def test_run_sends_five_briefings_with_the_country_wide_one_last(seed_db, monkeypatch, capsys):
    from src.newsletter import main

    t = _time_near_week_start()
    _make_db(
        seed_db,
        [
            _row("k1", "København opdatering", "Københavns Politi", t),
            _row("n1", "National opdatering", "Rigspolitiet", t),
        ],
    )
    sent = []

    def fake_send(label, *_a, **_k):
        sent.append(label)
        return {"region": label, "dry_run": True, "sent": False}

    monkeypatch.setattr(main.sender, "send_region_campaign", fake_send)
    main.run(36, 2026, dry_run=True)
    capsys.readouterr()

    assert sent == [*region_map.REGIONS, region_map.REGION_NATIONAL]


def test_run_skips_briefings_without_subscribers(seed_db, tmp_path, monkeypatch, capsys):
    from src.newsletter import main

    t = _time_near_week_start()
    _make_db(seed_db, [_row("k1", "København opdatering", "Københavns Politi", t)])
    monkeypatch.setattr(nconfig, "NEWSLETTER_STATE_PATH", str(tmp_path / "nl_state.json"))

    def fake_sync(label, dry_run=False):
        # Only the fallback audience has subscribers (the real state today).
        return 1 if label == region_map.REGION_NATIONAL else 0

    campaigns = []

    def fake_send(label, *_a, **_k):
        campaigns.append(label)
        return {"region": label, "sent": True}

    monkeypatch.setattr(main.sender, "sync_region_lists", fake_sync)
    monkeypatch.setattr(main.sender, "send_region_campaign", fake_send)

    main.run(36, 2026, dry_run=False)
    capsys.readouterr()

    # No campaign is created for an empty list; the country-wide one still goes.
    assert campaigns == [region_map.REGION_NATIONAL]

