"""Tests for the channel-kit generator (``src.distribute``).

The kit is built from the *published* digest archive, so the fixtures mirror
the real ``website/uge/{year}/{week}/digest.json`` shape that ``src.digest``
commits.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.distribute import generator, loader, main as distribute_main  # noqa: E402


def _digest(week: int = 37, year: int = 2026) -> dict:
    return {
        "week": week,
        "year": year,
        "total_posts": 128,
        "categories": {
            "missing_person": 4,
            "witness_appeal": 6,
            "arrest": 46,
            "other": 72,
        },
        "narrative": "Efterlysningen af Sara var ugens mest omtalte sag.",
        "narrative_html": "Efterlysningen af <a href=\"#\">Sara</a> var ugens mest omtalte sag.",
        "notable": [
            {
                "title": "Grundlovsforhør vedrørende drabsforsøg i Vildbjerg",
                "summary": "En mand blev fremstillet i grundlovsforhør.",
                "category": "arrest",
                "url": "https://x.com/PolitiUpdate/status/1",
            },
            {
                "title": "Nordsjællands Politi søger særligt vidne",
                "summary": "Politiet søger et særligt vidne.",
                "category": "witness_appeal",
                "url": "https://x.com/PolitiUpdate/status/2",
            },
        ],
        "category_items": {"arrest": [{"title": "Fængslet for stalking", "url": "u"}]},
        "region_items": {
            "Nordjylland": [{"title": "Savnet 18 årig mand i Frederikshavn", "url": "u1"}],
            "København": [
                {"title": "Demonstration i København", "url": "u2"},
                {"title": "Fængslet for stalking", "url": "u3"},
            ],
            "Kbh Vestegn": [{"title": "Sigtet for hærværk", "url": "u4"}],
            "Nordsjælland": [{"title": "Færdselsuheld ved Humlebæk", "url": "u5"}],
            "Sydsjælland/L-F": [{"title": "Indbrud i Næstved", "url": "u6"}],
            "Fyn": [{"title": "Anholdt efter vold i Odense", "url": "u7"}],
            "Anklagemyndigheden ved Midt-": [{"title": "Anke", "url": "u8"}],
        },
    }


@pytest.fixture
def published_dir(tmp_path):
    """A minimal published archive: weeks 36 and 37 of 2026."""
    root = tmp_path / "website" / "uge"
    for week, total in ((36, 18), (37, 128)):
        week_dir = root / "2026" / str(week)
        week_dir.mkdir(parents=True)
        payload = _digest(week=week)
        payload["total_posts"] = total
        (week_dir / "digest.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    return root


BASE = "https://politiupdates.dk"


# --- loader ---------------------------------------------------------------


def test_available_weeks_sorted(published_dir):
    assert loader.available_weeks(published_dir) == [(2026, 36), (2026, 37)]


def test_latest_week(published_dir):
    assert loader.latest_week(published_dir) == (2026, 37)


def test_latest_week_empty_raises(tmp_path):
    with pytest.raises(loader.DigestNotFoundError):
        loader.latest_week(tmp_path / "nope")


def test_load_missing_week_raises_with_hint(published_dir):
    with pytest.raises(loader.DigestNotFoundError) as exc:
        loader.load_digest(published_dir, 2026, 38)
    assert "git fetch" in str(exc.value)


def test_load_digest_rejects_non_digest_json(tmp_path):
    week_dir = tmp_path / "2026" / "37"
    week_dir.mkdir(parents=True)
    (week_dir / "digest.json").write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        loader.load_digest(tmp_path, 2026, 37)


def test_load_digest_fills_missing_optional_keys(tmp_path):
    week_dir = tmp_path / "2026" / "37"
    week_dir.mkdir(parents=True)
    (week_dir / "digest.json").write_text(
        '{"year": 2026, "week": 37, "total_posts": 3}', encoding="utf-8"
    )
    digest = loader.load_digest(tmp_path, 2026, 37)
    assert digest["categories"] == {} and digest["notable"] == []


def test_archive_url_has_no_tracking(published_dir):
    assert loader.archive_url(BASE + "/", 2026, 37) == f"{BASE}/uge/2026/37/"


# --- generator: regions + templates ---------------------------------------


@pytest.mark.parametrize(
    "label,expected",
    [
        ("Nordsjælland", generator.REGION_HOVEDSTADEN),
        ("Kbh Vestegn", generator.REGION_HOVEDSTADEN),
        ("København", generator.REGION_HOVEDSTADEN),
        ("Sydsjælland/L-F", generator.REGION_SJAELLAND),
        ("Nordjylland", generator.REGION_JYLLAND),
        ("Fyn", generator.REGION_FYN),
        ("Anklagemyndigheden ved Midt-", None),
    ],
)
def test_region_label_to_region(label, expected):
    assert generator.region_label_to_region(label) == expected


def test_region_items_flattens_and_excludes_unmapped():
    items = generator.region_items(_digest(), generator.REGION_HOVEDSTADEN)
    titles = [i["title"] for i in items]
    assert "Demonstration i København" in titles
    assert "Færdselsuheld ved Humlebæk" in titles
    assert "Anke" not in titles  # unmapped label is not attributed to a region


def test_region_with_most_items():
    assert generator.region_with_most_items(_digest()) == generator.REGION_HOVEDSTADEN


def test_region_with_no_items_returns_none():
    assert generator.region_with_most_items({"region_items": {}}) is None


def test_utm_link_appends_and_respects_existing_query():
    assert generator.utm_link("https://x.dk/a", "reddit", "uge37") == (
        "https://x.dk/a?utm_source=reddit&utm_medium=social&utm_campaign=uge37"
    )
    assert generator.utm_link("https://x.dk/a?p=1", "reddit", "uge37").startswith(
        "https://x.dk/a?p=1&utm_source=reddit"
    )


def test_reddit_post_contains_real_data_and_tracking():
    text = generator.build_reddit_post(_digest(), BASE)
    assert "128 meddelelser fra politiet i uge 37" in text
    assert "Efterlysningen af Sara" in text
    assert "Grundlovsforhør vedrørende drabsforsøg i Vildbjerg" in text
    assert "Efterlysninger/savnede: 4" in text
    assert f"{BASE}/uge/2026/37/?utm_source=reddit" in text
    assert generator.HONESTY_DISCLAIMER in text
    assert "regel 5" in text  # posting rule reminder travels with the draft


def test_reddit_post_never_claims_completeness():
    text = generator.build_reddit_post(_digest(), BASE)
    generator.assert_honest(text)  # must not raise
    for claim in generator.FORBIDDEN_CLAIMS:
        assert claim not in text.lower()


def test_assert_honest_rejects_completeness_claims():
    with pytest.raises(generator.DishonestCopyError):
        generator.assert_honest("Her er den fulde tekst af meddelelsen")


def test_reddit_post_without_narrative_or_notable():
    digest = _digest()
    digest["narrative"] = ""
    digest["notable"] = []
    text = generator.build_reddit_post(digest, BASE)
    assert "Ugens overblik: 128" in text
    assert "Ugens bemærkelsesværdige sager" not in text


def test_facebook_post_is_regional_and_counted():
    text = generator.build_facebook_post(_digest(), BASE, generator.REGION_HOVEDSTADEN)
    assert "Ugens politikort for Hovedstaden" in text
    assert "4 opdateringer i uge 37" in text  # 3 Hovedstaden items + 1 Vestegn
    assert f"utm_source=facebook" in text
    assert "Demonstration i København" in text
    assert "Savnet 18 årig mand" not in text  # other regions stay out


def test_facebook_post_region_with_no_items():
    text = generator.build_facebook_post(_digest(), BASE, generator.REGION_FYN)
    assert "1 opdatering i uge 37" in text


def test_x_post_is_link_free_and_within_limit():
    text = generator.build_x_post(_digest(), BASE)
    assert len(text) <= generator.X_MAX_CHARS
    assert "http" not in text
    assert "@PolitiUpdate" in text
    assert "Grundlovsforhør" in text


def test_x_post_trims_a_long_headline():
    digest = _digest()
    digest["notable"] = [{"title": "Lang sag " * 40, "summary": "x"}]
    text = generator.build_x_post(digest, BASE)
    assert len(text) <= generator.X_MAX_CHARS
    assert text.endswith("@PolitiUpdate")


def test_x_post_without_notable_picks():
    digest = _digest()
    digest["notable"] = []
    text = generator.build_x_post(digest, BASE)
    assert len(text) <= generator.X_MAX_CHARS


def test_build_summary_has_metrics_fields():
    summary = generator.build_summary(_digest(), BASE)
    assert summary["total_posts"] == 128
    assert summary["archive_url"] == f"{BASE}/uge/2026/37/"
    assert summary["tagged_urls"]["reddit"].endswith("utm_campaign=uge37")
    assert summary["notable"][0].startswith("Grundlovsforhør")


# --- CLI ------------------------------------------------------------------


def test_cli_list(published_dir, capsys):
    rc = distribute_main.main(["--list", "--published-dir", str(published_dir)])
    assert rc == 0
    assert capsys.readouterr().out.split() == ["2026-W36", "2026-W37"]


def test_cli_writes_drafts_and_summary(published_dir, tmp_path, capsys):
    out = tmp_path / "kit"
    rc = distribute_main.main(
        ["--published-dir", str(published_dir), "--out", str(out), "--site-base", BASE]
    )
    assert rc == 0
    names = sorted(p.name for p in out.iterdir())
    assert names == [
        "2026-W37-facebook.md",
        "2026-W37-reddit.md",
        "2026-W37-summary.json",
        "2026-W37-x.md",
    ]
    assert "Hovedstaden" in (out / "2026-W37-facebook.md").read_text(encoding="utf-8")
    assert "wrote" in capsys.readouterr().out


def test_cli_stdout_prints_drafts(published_dir, capsys):
    rc = distribute_main.main(
        ["--published-dir", str(published_dir), "--stdout", "--channel", "reddit"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "Ugens overblik: 128" in out
    assert "summary" in out


def test_cli_week_requires_published_data(published_dir, capsys):
    rc = distribute_main.main(
        ["--published-dir", str(published_dir), "--week", "38"]
    )
    assert rc == 2
    assert "no published digest" in capsys.readouterr().err


def test_cli_rejects_unknown_region(published_dir, capsys):
    rc = distribute_main.main(
        ["--published-dir", str(published_dir), "--region", "Jylland2"]
    )
    assert rc == 2
    assert "unknown region" in capsys.readouterr().err


def test_cli_specific_week_and_explicit_region(published_dir, tmp_path):
    out = tmp_path / "kit"
    rc = distribute_main.main(
        [
            "--published-dir", str(published_dir),
            "--week", "36", "--year", "2026",
            "--region", "Fyn",
            "--out", str(out),
        ]
    )
    assert rc == 0
    assert (out / "2026-W36-facebook.md").exists()
    assert "Fyn" in (out / "2026-W36-facebook.md").read_text(encoding="utf-8")
