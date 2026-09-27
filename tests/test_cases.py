"""Case identity: one briefing entry per case, not per posted update.

Rune's review of the delivered week-39 briefing (2026-09-27): highlights 3+5 were
the same case (Esbjerg, E. Hansens Vej) and 2+4 were the same case (Brøndbyøster
Station) — five slots showing three cases. These tests pin both real pairs, plus
the false merges that a looser rule produced when measured on weeks 38+39.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common import regions as region_map  # noqa: E402
from src.newsletter import cases, generator  # noqa: E402


# --- real wording from week 39 -------------------------------------------------

ESBJERG_TEASER = {
    "title": "Politiet til stede i Esbjerg",
    "body": "Vi er i øjeblikket til stede på E. Hansens Vej i Esbjerg, hvor vi "
            "undersøger et mistænkeligt forhold. Vi opdaterer hurtigst muligt.",
    "district": "Syd- og Sønderjyllands Politi",
    "x_post_id": "2101933951766122983",
    "guid": "https://via.ritzau.dk/pressemeddelelse/politiet-til-stede-i-esbjerg?publisherId=1#sm-1",
}
ESBJERG_MOBILE_STATION = {
    "title": "Vi er til stede med den mobile politistation på E. Hansensvej i Esbjerg",
    "body": "Den Mobile Politistation er til stede på E. Hansens Vej i Esbjerg i dag "
            "fra klokken 10.00 - 12.00. Kom forbi til en snak om din bydel og vores arbejde.",
    "district": "Syd- og Sønderjyllands Politi",
    "x_post_id": "2102310434816831998",
    "guid": "https://via.ritzau.dk/pressemeddelelse/mobile-politistation-esbjerg?publisherId=1#sm-3",
}
BRONDBY_EPISODE = {
    "title": "Episode på Brøndbyøster Station",
    "body": "Vi er i øjeblikket til stede i forbindelse med en episode på Brøndbyøster "
            "Station. Vi opfordrer til at følge vores anvisninger.",
    "district": "Københavns Vestegns Politi",
    "x_post_id": "2102756404889354495",
    "guid": "https://via.ritzau.dk/pressemeddelelse/episode-broendbyoester?publisherId=1#sm-2",
}
BRONDBY_COURT = {
    "title": "Ung mand varetægtsfængslet i fire uger for grov vold",
    "body": "Retten i Glostrup har i dag valgt at varetægtsfængsle en ung mand i fire uger "
            "for grov vold. Han er også mistænkt for forsøg på manddrab ved en episode, der "
            "fandt sted på Brøndbyøster Station den 23. september.",
    "district": "Anklagemyndigheden ved Københavns Vestegns Politi",
    "x_post_id": "2103129285880090864",
    "guid": "https://via.ritzau.dk/pressemeddelelse/varetaegtsfaengsling-grov-vold?publisherId=1#sm-4",
}


def test_one_press_release_page_is_one_case():
    """The same page re-announced under a new #sm- id is one case, not three."""
    pool = [dict(ESBJERG_TEASER, x_post_id=str(n), guid=ESBJERG_TEASER["guid"].replace("#sm-1", f"#sm-{n}"))
            for n in range(3)]
    clusters = cases.group_by_case(pool)
    assert len(clusters) == 1
    assert cases.represent(clusters[0], {})["updates"] == 3


def test_two_pages_about_the_same_case_merge_on_the_venue():
    """Esbjerg (highlights 3+5): two pages, two wordings, one case."""
    clusters = cases.group_by_case([ESBJERG_TEASER, ESBJERG_MOBILE_STATION])
    assert len(clusters) == 1
    # both spellings of the address ("E. Hansensvej" / "E. Hansens Vej") land on
    # the same normalised key
    assert "ehansensvej" in cases.venues(ESBJERG_TEASER) & cases.venues(ESBJERG_MOBILE_STATION)


def test_court_outcome_merges_with_the_incident_it_follows():
    """Brøndbyøster (highlights 2+4): the incident and its outcome, wrapper and all.

    The prosecution message carries the district as "Anklagemyndigheden ved
    Københavns Vestegns Politi" — without stripping that wrapper the two posts
    look like two different districts and the case stays split.
    """
    clusters = cases.group_by_case([BRONDBY_EPISODE, BRONDBY_COURT])
    assert len(clusters) == 1


def test_unrelated_cases_in_one_district_stay_apart():
    """Two missing-person cases are not one case just because the words overlap."""
    first = {
        "title": "Efterlysning: 73-årig mand er gået fra adressen XX i Skive",
        "body": "Vi søger lige nu efter en 73-årig mand, som er gået fra adressen i Skive.",
        "district": "Midt- og Vestjyllands Politi", "x_post_id": "1", "guid": "https://a/#sm-1",
    }
    second = {
        "title": "Politiet søger vidner efter brand i Tylstrup",
        "body": "Vi søger vidner, efter at der natten til torsdag var brand på en adresse i Tylstrup.",
        "district": "Nordjyllands Politi", "x_post_id": "2", "guid": "https://b/#sm-2",
    }
    assert len(cases.group_by_case([first, second])) == 2


def test_two_motorways_are_not_one_venue():
    """A bare road type ("motorvejen") must never become a case anchor."""
    east = {
        "title": "Færdselsuheld på Østjyske Motorvej",
        "body": "Der er sket et færdselsuheld på Østjyske Motorvej ved Horsens.",
        "district": "Sydøstjyllands Politi", "x_post_id": "1", "guid": "https://a/#sm-1",
    }
    west = {
        "title": "Færdselsuheld på Vestmotorvejen",
        "body": "Der er sket et færdselsuheld på Vestmotorvejen mellem Slagelse og Sorø.",
        "district": "Sydsjællands og Lolland-Falsters Politi", "x_post_id": "2", "guid": "https://b/#sm-2",
    }
    assert cases.venues(east) == {"østjyskemotorvej"}
    # a bare named motorway is not an anchor either: two pile-ups on the same
    # motorway in one week are two cases, and "motorvej"/"motorvejen" alone would
    # merge every accident on every motorway in the district
    assert cases.venues(west) == set()
    assert len(cases.group_by_case([east, west])) == 2


def test_represent_shows_the_newest_update_and_never_hides_the_count():
    cluster = cases.group_by_case([BRONDBY_EPISODE, BRONDBY_COURT])[0]
    entry = cases.represent(cluster, {"2102756404889354495": 160, "2103129285880090864": 40})
    assert entry["post"]["x_post_id"] == "2103129285880090864"   # the outcome, newest
    assert entry["link_post"] is entry["post"]                   # text and link agree
    assert entry["updates"] == 2
    assert entry["rank_views"] == 160                            # ranked by reach


def test_a_stub_never_wins_over_a_real_update():
    cluster = cases.group_by_case([ESBJERG_TEASER, ESBJERG_MOBILE_STATION])[0]
    entry = cases.represent(cluster, {"2101933951766122983": 2643, "2102310434816831998": 83})
    assert entry["post"]["x_post_id"] == "2102310434816831998"
    assert entry["rank_views"] == 2643


def test_briefing_top_slot_lists_five_distinct_cases_and_links_x():
    """Five slots, five cases, and every one says where the full story is."""
    posts = [ESBJERG_TEASER, ESBJERG_MOBILE_STATION, BRONDBY_EPISODE, BRONDBY_COURT]
    posts += [
        {"title": f"Sag {n}", "body": f"En helt anden sag nummer {n} i ugen.",
         "district": "Østjyllands Politi", "x_post_id": f"9{n}",
         "guid": f"https://c{n}/#sm-1", "posted_at": f"2026-09-2{n}T08:00:00"}
        for n in range(1, 5)
    ]
    views = {ESBJERG_TEASER["x_post_id"]: 2643, ESBJERG_MOBILE_STATION["x_post_id"]: 83,
             BRONDBY_EPISODE["x_post_id"]: 160, BRONDBY_COURT["x_post_id"]: 40,
             "91": 150, "92": 120, "93": 90, "94": 60}

    brief = generator.generate(region_map.REGION_HOVEDSTADEN, posts, 39, 2026, views=views)
    highlights = brief["highlights"]
    assert len(highlights) == 5
    assert len({h["url"] for h in highlights}) == 5            # five distinct cases
    assert [h["views"] for h in highlights] == [2643, 160, 150, 120, 90]
    # the reader is told, in the mail itself, where the full post lives
    assert brief["text"].count("Læs hele opslaget på X:") == 5
    assert brief["html"].count("Læs hele opslaget på X") == 5
    assert "(2 opdateringer i sagen)" in brief["text"]
    assert "2 opdateringer i sagen" in brief["html"]
