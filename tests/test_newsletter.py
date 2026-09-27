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


def test_briefing_links_back_to_the_owned_archive_page():
    """Every briefing must point at that week's page on our own domain.

    The briefing was previously a dead end for the funnel: it carried only X
    links, so a subscriber could not reach the site (and its signup form) at
    all. The link must use the canonical .dk host — never the github.io URL
    that only 301s there.
    """
    posts = [
        {"title": "Efterlysning", "district": "Fyns Politi", "body": "Første linje", "x_post_id": "123"}
    ]
    brief = generator.generate(region_map.REGION_FYN, posts, 38, 2026)
    url = "https://politiupdates.dk/uge/2026/38/"
    assert url in brief["text"]
    assert f'href="{url}"' in brief["html"]
    assert "runestone0.github.io" not in brief["text"] + brief["html"]


def test_briefing_site_link_follows_the_configured_base(monkeypatch):
    monkeypatch.setattr(nconfig, "SITE_BASE_URL", "https://example.test")
    assert generator.archive_url(38, 2026) == "https://example.test/uge/2026/38/"
    posts = [{"title": "T", "district": "", "body": "B", "x_post_id": "1"}]
    brief = generator.generate(region_map.REGION_NATIONAL, posts, 5, 2026)
    # unpadded week, matching the digest publisher's archive paths
    assert "https://example.test/uge/2026/5/" in brief["text"]
    assert 'href="https://example.test/uge/2026/5/"' in brief["html"]


# --- A briefing must not print the same item twice ---------------------------
#
# The feed re-announces one press-release page under a new id on every police
# update, and each update is posted as its own tweet (deliberately: an "afblæst"
# update must be shareable). Inside a *briefing* that reads as a broken feed:
# the briefing actually delivered for week 38 (campaign 6, measured 2026-09-26)
# listed 136 items of which 3 repeated an earlier item verbatim.


def test_briefing_lists_a_verbatim_repeat_once():
    post = {"title": "Straksdom for indbrud", "district": "Københavns Politi",
            "body": "Vi modtog lørdag anmeldelse fra en borger.", "x_post_id": "1"}
    repeat = dict(post, x_post_id="2")  # same page re-announced under a new id
    brief = generator.generate(region_map.REGION_HOVEDSTADEN, [post, repeat], 39, 2026)
    assert brief["text"].count("Straksdom for indbrud") == 1
    assert brief["html"].count("Straksdom for indbrud") == 1
    # ... but the count stays the week's real number of updates
    assert "(2 opdateringer)" in brief["subject"]


def test_briefing_index_lists_a_story_once_and_links_its_newest_update():
    """Same headline + new body = one *story* in the index, linked to newest.

    `dedupe_visible` (asserted below) keeps both rows as separate items; the
    briefing's index then collapses them, because two lines reading
    "Metro-trafikken på Cityringen midt. indstillet" are indistinguishable to a
    reader — measured on the delivered week-38 copy, where 47 of 136 rows
    repeated a headline already in the list. The link follows the story's
    NEWEST post, so the "metroen kører igen" update is one tap away, and the
    count stays the week's real number of updates.
    """
    appeal = {"title": "Metro-trafikken på Cityringen midlertidigt indstillet",
              "district": "Københavns Politi",
              "body": "Vi er i øjeblikket til stede i et tunnelrør.", "x_post_id": "1"}
    resolved = dict(appeal, body="Vi er nu færdige med vores undersøgelser, og metroen kører igen.",
                    x_post_id="2")
    brief = generator.generate(region_map.REGION_HOVEDSTADEN, [appeal, resolved], 39, 2026)
    assert brief["text"].count("Metro-trafikken på Cityringen") == 1
    assert "status/2" in brief["text"] and "status/1" not in brief["text"]
    assert 'href="https://x.com/PolitiUpdate/status/2"' in brief["html"]
    # the follow-up is not silently lost: the index entry knows it had 2 updates
    assert "(2 opdateringer)" in brief["subject"]


def test_dedupe_visible_keys_on_what_the_reader_sees():
    a = {"title": "Titel", "district": "Fyns Politi", "body": "Første linje.\n\nResten.", "x_post_id": "1"}
    b = dict(a, x_post_id="2")                      # identical visible block
    c = dict(a, district="Nordjyllands Politi")     # another district -> different entry
    d = dict(a, body="Anden første linje.\n\nResten.")  # different first line -> an update
    assert generator.dedupe_visible([a, b, c, d]) == [a, c, d]
    assert generator.visible_key(a) == generator.visible_key(b) != generator.visible_key(d)


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


# --- A briefing leads with the week's most READ stories ----------------------
#
# Reworked 2026-09-26 against the copy that was actually delivered (campaign 6,
# week 38: 136 items / 44 KB of text / 136 x.com hrefs and nothing else). X view
# counts come from src/common/x_reach.py and decide the ranking only.

_FOOTBALL = "FODBOLDKAMP I BRØNDBY"


def _football_posts():
    """The real week-38 shape: one story re-announced 5×, plus a few others."""
    return [
        {"title": _FOOTBALL, "district": "Københavns Vestegns Politi",
         "body": f"Politiet er til stede ved Brøndby Stadion. Opdatering {n}.",
         "x_post_id": str(n), "posted_at": f"2026-09-20T0{n}:00:00"} for n in range(5)
    ] + [
        {"title": "Politiet indfører visitationszone ved Brøndby-FCK kamp",
         "district": "Københavns Vestegns Politi", "body": "Visitationszonen gælder fra kl. 12.",
         "x_post_id": "90", "posted_at": "2026-09-15T07:36:00"},
        {"title": "43-årig mand fra Silkeborg varetægtsfængslet",
         "district": "Midt- og Vestjyllands Politi", "body": "Manden er fængslet i fire uger.",
         "x_post_id": "91", "posted_at": "2026-09-16T11:08:00"},
    ]


def test_highlight_block_leads_with_the_most_read_distinct_story():
    posts = _football_posts() + [
        {"title": "Sprængning i Vorre ved Skødstrup - ingen kommet til skade",
         "district": "Østjyllands Politi", "body": "Ingen personer kom til skade.",
         "x_post_id": "92", "posted_at": "2026-09-17T05:00:00"}
    ]
    views = {"0": 172, "1": 146, "2": 143, "3": 126, "4": 74, "90": 74, "91": 58}
    brief = generator.generate(region_map.REGION_HOVEDSTADEN, posts, 38, 2026, views=views)

    titles = [h["title"] for h in brief["highlights"]]
    # The same headline 5× must not fill the block: one entry per story.
    assert titles == [_FOOTBALL, "Politiet indfører visitationszone ved Brøndby-FCK kamp",
                      "43-årig mand fra Silkeborg varetægtsfængslet"]
    assert brief["highlights"][0]["views"] == 172
    # ... and the highest-viewed of the repeats is the one that links out
    assert brief["highlights"][0]["url"].endswith("/0")
    # a story shown as a highlight is never repeated in the index below it
    index_block = brief["text"].split("FLERE SAGER FRA UGEN")[1]
    assert "Brøndby" not in index_block
    assert "Skødstrup" in index_block


def test_highlight_block_is_collapsed_for_repeats_and_never_duplicated():
    posts = _football_posts()
    views = {str(n): 100 - n for n in range(5)}  # only one story has any reach
    brief = generator.generate(region_map.REGION_HOVEDSTADEN, posts, 38, 2026, views=views)
    assert len(brief["highlights"]) == 1
    assert brief["text"].count(_FOOTBALL) == 1
    assert brief["html"].count(_FOOTBALL) == 1


def test_subject_leads_with_the_most_read_story_not_a_count():
    posts = _football_posts()
    views = {"0": 172, "90": 74}
    brief = generator.generate(region_map.REGION_HOVEDSTADEN, posts, 38, 2026, views=views)
    assert brief["subject"] == "Ugens mest læste: FODBOLDKAMP I BRØNDBY"
    assert "(136 opdateringer)" not in brief["subject"]
    assert len(brief["subject"]) <= 45 + len("Ugens mest læste: ")


def test_subject_keeps_the_count_when_there_is_no_reach():
    posts = _football_posts()
    brief = generator.generate(region_map.REGION_HOVEDSTADEN, posts, 38, 2026)
    assert brief["subject"] == "PolitiUpdate · Hovedstaden · uge 38, 2026 (7 opdateringer)"
    assert brief["highlights"] == []


def test_headlines_are_mirrored_verbatim():
    """No case rewriting: a mangled place name is worse than a shouty headline."""
    assert generator.display_title(_FOOTBALL) == _FOOTBALL
    assert generator.display_title("Kbh Vestegn: Politiet indfører visitationszone") == (
        "Kbh Vestegn: Politiet indfører visitationszone"
    )


def test_index_is_capped_and_says_how_many_stories_are_left(monkeypatch):
    monkeypatch.setattr(nconfig, "NEWSLETTER_INDEX_LIMIT", 3)
    posts = [
        {"title": f"Sag nummer {n}", "district": "Fyns Politi", "body": f"Body {n}",
         "x_post_id": str(n), "posted_at": f"2026-09-14T0{n}:00:00"}
        for n in range(7)
    ]
    brief = generator.generate(region_map.REGION_FYN, posts, 38, 2026)
    assert brief["text"].count("- Fyn: Sag nummer") == 3
    # the count in the copy stays the week's real number of updates
    assert "7 opdateringer" in brief["text"]
    assert "og 4 flere sager" in brief["html"]
    assert brief["stories"] == 7


def test_briefing_renders_escaped_copy_and_one_primary_cta():
    posts = [
        {"title": "Fundet <script>alert(1)</script>", "district": "Fyns Politi",
         "body": "A & B", "x_post_id": "5", "posted_at": "2026-09-14T08:00:00"}
    ]
    brief = generator.generate(region_map.REGION_FYN, posts, 38, 2026, views={"5": 12})
    assert "<script>" not in brief["html"]
    assert "&lt;script&gt;" in brief["html"]
    assert "A &amp; B" in brief["html"]
    assert "Se alle 1 opdateringer" in brief["html"]


def test_summary_cuts_on_a_word_boundary():
    long_body = "En meget lang sætning " * 20
    out = generator.summary(long_body, 40)
    assert len(out) <= 43
    assert out.endswith(" …")
    assert "  " not in out


def _briefing_html(posts=None, views=None):
    posts = posts or [
        {"title": "Efterlysning: 74-årig kvinde savnet", "district": "Sydsjællands og Lolland-Falsters Politi",
         "body": "Vi efterlyser en kvinde, der er gået fra sit hjem.\n\nHun er sidst set i Slagelse.",
         "x_post_id": "111", "posted_at": "2026-09-14T08:00:00"},
        {"title": "Brand i krydstogtskib", "district": "Bornholms Politi",
         "body": "Politi og brandvæsen er til stede ved kajen.", "x_post_id": "222",
         "posted_at": "2026-09-15T08:00:00"},
    ]
    return generator.generate(
        region_map.REGION_NATIONAL, posts, 38, 2026, views=views or {"111": 55, "222": 21}
    )["html"]


def test_briefing_html_is_email_safe():
    """Email-safe by construction: inline styles, no external assets, absolute links.

    An inbox is not a browser: no <style>/<script>, no images or fonts fetched
    from a third party, no relative URL (there is no base URL in mail), and only
    one 600px column so it renders on a phone. The delivered campaign 6 was a
    bare <ul> of 136 items with no wrapper at all, which is also why it had no
    preheader: inboxes showed whichever raw sentence happened to come first.
    """
    from html.parser import HTMLParser

    html = _briefing_html()

    class Parser(HTMLParser):
        VOID = {"br", "img", "meta", "hr", "input", "link"}

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack: list[str] = []
            self.errors: list[str] = []
            self.tags: list[str] = []
            self.hrefs: list[str] = []

        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
            if tag not in self.VOID:
                self.stack.append(tag)
            for name, value in attrs:
                if name == "href":
                    self.hrefs.append(value)

        def handle_endtag(self, tag):
            if tag in self.VOID:
                return
            if not self.stack or self.stack[-1] != tag:
                self.errors.append(f"unbalanced </{tag}> (open: {self.stack[-3:]})")
                return
            self.stack.pop()

    parser = Parser()
    parser.feed(html)

    assert parser.errors == []
    assert parser.stack == []
    assert "<script" not in html.lower() and "<style" not in html.lower()
    assert "<img" not in html.lower() and "<link" not in html.lower()
    assert 'charset="utf-8"' in html and 'lang="da"' in html
    assert "max-width:600px" in html
    assert parser.hrefs, "a briefing without links is a dead end"
    for href in parser.hrefs:
        assert href.startswith("https://"), href
        assert href.split("/")[2] in {"x.com", "politiupdates.dk"}, href
    # links use a plain ASCII host: the .dk domain must never arrive punycoded
    assert "xn--" not in html


def test_briefing_html_has_a_preheader_and_the_real_count():
    html = _briefing_html()
    assert "2 opdateringer fra politiet i hele landet i uge 38" in html
    assert "Se alle 2 opdateringer" in html


def test_dry_run_does_not_look_up_reach_unless_asked(seed_db, monkeypatch, capsys):
    from src.newsletter import main

    t = _time_near_week_start()
    _make_db(seed_db, [_row("k1", "København opdatering", "Københavns Politi", t)])
    calls = []

    def fake_fetch(ids, **_k):
        calls.append(list(ids))
        return {}

    monkeypatch.setattr(main.x_reach, "fetch_views", fake_fetch)
    monkeypatch.setattr(main.sender, "send_region_campaign",
                        lambda *a, **k: {"region": a[0], "dry_run": True, "sent": False})

    main.run(36, 2026, dry_run=True)
    capsys.readouterr()
    assert calls == []  # a preview must not touch the network by default

    main.run(36, 2026, dry_run=True, reach=True)
    capsys.readouterr()
    assert calls == [["x-k1"]]


def test_reach_failure_never_blocks_the_send(seed_db, tmp_path, monkeypatch, capsys):
    from src.newsletter import main

    t = _time_near_week_start()
    _make_db(seed_db, [_row("k1", "København opdatering", "Københavns Politi", t)])
    # isolate the sent-week marker: a real send writes it, and a test that picks
    # up another test's marker would silently skip the send it is asserting on
    monkeypatch.setattr(nconfig, "NEWSLETTER_STATE_PATH", str(tmp_path / "nl_state.json"))

    def boom(*_a, **_k):
        raise RuntimeError("fxtwitter is down")

    monkeypatch.setattr(main.x_reach, "fetch_views", boom)
    monkeypatch.setattr(main.sender, "sync_region_lists", lambda *a, **k: 1)
    sent = []
    monkeypatch.setattr(main.sender, "send_region_campaign",
                        lambda label, *a, **k: sent.append(label) or {"region": label, "sent": True})

    main.run(36, 2026, dry_run=False, reach=True)
    capsys.readouterr()
    assert region_map.REGION_NATIONAL in sent

