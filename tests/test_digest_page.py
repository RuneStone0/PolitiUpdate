"""The archive page's structure: one row per case, a lead block, quiet links.

The page is the newsletter's public counterpart (it is the link the briefing
sends readers to), so these tests pin the two things Rune asked for on
2026-09-27: the week is readable at a glance — the same hierarchy as the mail,
with human dates and a most-read lead — and the case list stops repeating one
case three times, without the whole section lighting up blue.
"""

import pytest

from src.digest import main as digest_main, publisher


def _post(title, *, post_id="1", case=None, updates=None, primary=False, body=""):
    post = {"title": title, "x_post_id": post_id, "body": body or title}
    if case:
        post["case"] = case
        post["updates"] = updates if updates is not None else 1
    if primary:
        post["primary"] = True
    return post


# --- week range label -------------------------------------------------------


def test_week_range_label_names_the_days_a_reader_can_place():
    assert publisher.week_range_label(2026, 39) == "21.–27. september 2026"


def test_week_range_label_spans_two_months():
    assert publisher.week_range_label(2026, 18) == "27. april – 3. maj 2026"


def test_week_range_label_handles_the_year_boundary():
    # ISO week 1 of 2027 starts 2027-01-04, so it stays inside January.
    assert publisher.week_range_label(2027, 1) == "4.–10. januar 2027"
    # Week 53 of 2026 ends in 2027: both years must appear, not just one.
    assert publisher.week_range_label(2026, 53) == "28. december 2026 – 3. januar 2027"


# --- case collapsing --------------------------------------------------------


def test_case_rows_collapse_updates_of_one_case_onto_its_primary_row():
    items = [
        {"title": "Brand på adresse i Trige", "url": "u1", "case": "a", "updates": 3},
        {"title": "Brand på adresse i Trige", "url": "u2", "case": "a", "updates": 3},
        {
            "title": "Brand på adresse i Trige — slukket",
            "url": "u3",
            "case": "a",
            "updates": 3,
            "primary": True,
        },
        {"title": "Kænguru ved landevejen", "url": "u4", "case": "b", "updates": 1},
    ]
    rows = publisher._case_rows(items)

    assert [row["title"] for row in rows] == [
        "Brand på adresse i Trige — slukket",  # the case's newest word
        "Kænguru ved landevejen",
    ]
    assert [row["updates"] for row in rows] == [3, 1]
    assert rows[0]["url"] == "u3"


def test_case_rows_without_case_keys_fall_back_to_the_headline():
    """Weeks published before the digest baked in a case key still collapse —
    the 2–3 repeats per case were usually the identical headline. The row shown
    is the newest of them, like every other collapsed case."""
    items = [
        {"title": "Metro-trafikken på Cityringen midlertidigt indstillet", "url": "u1"},
        {"title": "Metro-trafikken  på Cityringen   midlertidigt indstillet", "url": "u2"},
        {"title": "Kbh Syd Station.", "url": "u3"},
    ]
    rows = publisher._case_rows(items)

    assert [row["url"] for row in rows] == ["u2", "u3"]
    assert rows[0]["title"].split() == "Metro-trafikken på Cityringen midlertidigt indstillet".split()
    assert rows[0]["updates"] == 2


def test_different_cases_are_never_merged():
    items = [
        {"title": "Færdselsuheld på Østjyske Motorvej", "url": "u1", "case": "a"},
        {"title": "Færdselsuheld på Vestmotorvejen", "url": "u2", "case": "b"},
    ]
    assert len(publisher._case_rows(items)) == 2


# --- index rendering --------------------------------------------------------


def test_index_rows_are_links_but_stay_visually_quiet():
    html = publisher._render_cat_items(
        [{"title": "Kbh Syd Station.", "url": "https://x.com/PolitiUpdate/status/1", "case": "a"}]
    )

    assert 'class="case-row"' in html
    assert 'class="row-arrow"' in html
    assert "text-decoration" not in html  # styling lives in digest.css, not inline
    assert "#93c5fd" not in html and "#1d4ed8" not in html


def test_index_row_mentions_the_updates_that_were_collapsed():
    html = publisher._render_cat_items(
        [{"title": "Eftersøgning af 91-årig kvinde i Randers", "url": "u", "case": "a", "updates": 3}]
    )
    assert "3 opdateringer" in html


def test_single_update_rows_do_not_claim_an_update_count():
    html = publisher._render_cat_items([{"title": "Kbh Syd Station.", "url": "u", "case": "a"}])
    assert "opdateringer" not in html


def test_accordion_badge_counts_cases_and_names_the_updates_behind_them():
    groups = [
        (
            "Øvrige meddelelser",
            [
                {"title": "Brand på adresse i Trige", "url": "u1", "case": "a", "updates": 3},
                {"title": "Brand på adresse i Trige", "url": "u2", "case": "a", "updates": 3},
                {"title": "Brand på adresse i Trige", "url": "u3", "case": "a", "updates": 3},
                {"title": "Kbh Syd Station.", "url": "u4", "case": "b", "updates": 1},
            ],
        )
    ]
    html = publisher._render_accordion(groups)

    assert '<span class="cat-count">2</span>' in html  # two cases, not four rows
    assert '<span class="cat-meta">4 opdateringer</span>' in html


def test_accordion_without_repeats_has_no_update_note():
    html = publisher._render_accordion([("Nordjylland", [{"title": "X", "url": "u", "case": "a"}])])
    assert "cat-meta" not in html


# --- most-read lead ---------------------------------------------------------


def test_highlights_render_the_same_block_the_mail_leads_with():
    digest = {
        "week": 39,
        "highlights": [
            {
                "title": "Kænguru ved landevejen Tykhøjetvej i Give",
                "summary": "En kænguru blev set ved landevejen.",
                "url": "https://x.com/PolitiUpdate/status/2103001189495554450",
                "updates": 2,
                "views": 2643,
            }
        ],
    }
    html = publisher._render_highlights(digest)

    assert "Ugens mest læste sager" in html
    assert 'class="highlight-card"' in html
    assert 'class="highlight-rank">1<' in html
    assert "Læs hele opslaget på X" in html
    assert "2 opdateringer i sagen" in html


def test_highlights_section_is_dropped_without_reach_data():
    """No view counts means no "most read" claim — the section disappears
    rather than ranking cases by nothing."""
    assert publisher._render_highlights({"week": 39, "highlights": []}) == ""
    assert publisher._render_highlights({"week": 39}) == ""


def test_highlights_without_a_link_are_skipped():
    digest = {"week": 39, "highlights": [{"title": "Uden link", "summary": "x", "url": ""}]}
    assert publisher._render_highlights(digest) == ""


# --- the page as a whole ----------------------------------------------------


MINIMAL = {
    "week": 39,
    "year": 2026,
    "total_posts": 4,
    "case_count": 3,
    "categories": {"missing_person": 1, "witness_appeal": 0, "arrest": 1, "other": 2},
    "narrative": "Ugen i korte træk.",
    "narrative_html": "Ugen i korte træk.",
    "notable": [],
    "category_items": {
        "missing_person": [{"title": "Savnet kvinde", "url": "u1", "case": "a"}],
        "witness_appeal": [],
        "arrest": [{"title": "Anholdt", "url": "u2", "case": "b"}],
        "other": [
            {"title": "Brand i Trige", "url": "u3", "case": "c", "updates": 2},
            {"title": "Brand i Trige", "url": "u4", "case": "c", "updates": 2, "primary": True},
        ],
    },
    "region_items": {"Nordjylland": [{"title": "Savnet kvinde", "url": "u1", "case": "a"}]},
    "highlights": [
        {
            "title": "Savnet kvinde",
            "summary": "En kvinde blev efterlyst.",
            "url": "u1",
            "updates": 1,
            "views": 100,
        }
    ],
    "prev_week": {"year": 2026, "week": 38},
    "next_week": None,
}


def test_page_leads_with_the_highlights_and_names_the_week_by_its_dates():
    html = publisher._render_archive_html(MINIMAL)

    assert html.index('class="digest-highlights"') < html.index('class="digest-narrative"')
    assert "21.–27. september 2026" in html
    assert "93 opdateringer" not in html  # this digest has 4, and says so
    assert "4 opdateringer" in html and "3 sager" in html


def test_page_labels_the_breakdown_as_the_week_s_cases_not_statistics():
    html = publisher._render_archive_html(MINIMAL)

    assert "Alle ugens sager" in html
    assert "Statistik" not in html


def test_page_keeps_the_signup_block_and_the_pager():
    html = publisher._render_archive_html(MINIMAL)

    assert 'class="digest-signup"' in html
    assert 'class="pager-link pager-prev"' in html


# --- data layer: annotate_cases --------------------------------------------


def test_annotate_cases_tags_every_post_and_marks_one_primary_row():
    posts_by_category = {
        "other": [
            {
                "title": "Brand på adresse i Trige",
                "body": "Der udbrød brand.",
                "x_post_id": "1",
                "guid": "page-1",
            },
            {
                "title": "Brand på adresse i Trige",
                "body": "Branden er slukket.",
                "x_post_id": "2",
                "guid": "page-1",
            },
        ],
        "arrest": [
            {"title": "Anholdt efter brand", "body": "En mand blev anholdt.", "x_post_id": "3", "guid": "page-2"}
        ],
        "missing_person": [],
        "witness_appeal": [],
    }
    views = {"1": 10, "2": 40, "3": 5}
    case_count, highlights = digest_main.annotate_cases(posts_by_category, views)

    assert case_count == 2
    for posts in posts_by_category.values():
        for post in posts:
            assert post["case"], "every published row must carry its case key"
    trige = posts_by_category["other"]
    assert trige[0]["case"] == trige[1]["case"]
    assert trige[0]["updates"] == trige[1]["updates"] == 2
    assert sum(1 for post in trige if post.get("primary")) == 1
    # ranked by the case's most-viewed update, so the Trige case (40) leads
    assert [h["title"] for h in highlights] == ["Brand på adresse i Trige", "Anholdt efter brand"]
    assert highlights[0]["views"] == 40


def test_annotate_cases_without_views_returns_no_highlights():
    posts_by_category = {
        "other": [{"title": "Kbh Syd Station.", "body": "x", "x_post_id": "1", "guid": "p"}],
        "arrest": [],
        "missing_person": [],
        "witness_appeal": [],
    }
    case_count, highlights = digest_main.annotate_cases(posts_by_category, {})

    assert case_count == 1
    assert highlights == []


def test_published_entry_carries_the_case_without_leaking_the_body():
    entry = digest_main._entry(
        {"title": "Savnet kvinde", "x_post_id": "2101976895357346194", "case": "2101976895357346194", "updates": 3}
    )
    assert entry == {
        "title": "Savnet kvinde",
        "url": "https://x.com/PolitiUpdate/status/2101976895357346194",
        "case": "2101976895357346194",
        "updates": 3,
    }


@pytest.mark.parametrize("week", [1, 26, 52])
def test_week_range_label_always_produces_a_label(week):
    assert publisher.week_range_label(2026, week)
