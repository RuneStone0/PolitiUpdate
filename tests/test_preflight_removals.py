"""The push gate's rules about lines that disappear from a published page.

``scripts/preflight-push.py --compare-live`` diffs a re-rendered page against the
served one and treats a removed line as benign only in named ways. The 2026-09-27
archive restructure added a third way — a case's rows collapse into one — and an
allowance that is too broad turns the gate off. These tests pin both halves: the
collapse is accepted *with evidence*, and a case item that is gone from the data
too still fails.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "preflight-push.py"

_spec = importlib.util.spec_from_file_location("preflight_push", SCRIPT)
assert _spec and _spec.loader
preflight = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preflight)


DIGEST = """{
  "category_items": {
    "other": [
      {"title": "Røgudvikling fra McDonald's i Brøndbyøster,", "url": "https://x.com/PolitiUpdate/status/111"}
    ]
  }
}"""


def test_collapsed_update_row_is_benign_when_the_data_still_has_it():
    line = (
        '<li><a href="https://x.com/PolitiUpdate/status/111" target="_blank" '
        'rel="noopener">Røgudvikling fra McDonald&#x27;s i Brøndbyøster,</a></li>'
    )
    assert preflight._benign_removal(line, local_text="<p>new page</p>", digest_text=DIGEST)


def test_collapsed_update_row_without_data_backing_is_a_regression():
    """The exact thing the gate exists for: a case item silently dropped."""
    line = (
        '<li><a href="https://x.com/PolitiUpdate/status/999" target="_blank" '
        'rel="noopener">En sag der er væk</a></li>'
    )
    assert not preflight._benign_removal(line, local_text="<p>new page</p>", digest_text=DIGEST)


def test_legacy_row_is_not_excused_by_the_shape_alone():
    line = (
        '<li><a href="https://x.com/PolitiUpdate/status/111" target="_blank" '
        'rel="noopener">En helt anden overskrift end i data</a></li>'
    )
    assert not preflight._benign_removal(line, local_text="<p>new page</p>", digest_text=DIGEST)
    # ...and with no digest.json to check against, the shape proves nothing
    assert not preflight._benign_removal(line, local_text="<p>new page</p>")


@pytest.mark.parametrize(
    "line",
    [
        '<p class="digest-meta">93 Opdateringer</p>',
        "<h2>Statistik</h2>",
        '<summary><span class="cat-count">12</span><span class="cat-label">Efterlysninger/savnede</span></summary>',
    ],
)
def test_the_restructure_s_replaced_lines_are_benign(line):
    assert preflight._benign_removal(line, local_text="<p>new page</p>", digest_text=DIGEST)


def test_a_lost_pager_link_is_still_a_regression():
    line = '<a class="pager-link pager-prev" href="../../2026/38/">&larr; Uge 38, 2026</a>'
    assert not preflight._benign_removal(line, local_text="<p>new page</p>", digest_text=DIGEST)


def test_content_that_survived_elsewhere_in_the_page_is_benign():
    assert preflight._benign_removal('<li>Kbh Syd Station.</li>', local_text="<li>Kbh Syd Station.</li>")


def test_digest_evidence_reads_values_not_json_escapes(tmp_path):
    """A title with a quote in it is evidence in the page's escaped form only
    because the JSON's own escaping is stripped away first."""
    path = tmp_path / "digest.json"
    path.write_text(
        json.dumps(
            {"category_items": {"witness_appeal": [
                {"title": 'Vidner søges til overfald under "Rockbæk"', "url": "https://x/1"}
            ]}}
        ),
        encoding="utf-8",
    )
    evidence = preflight._digest_evidence(path)

    assert 'Vidner søges til overfald under "Rockbæk"' in evidence
    line = (
        '<li><a href="https://x/1" target="_blank" rel="noopener">'
        "Vidner søges til overfald under &quot;Rockbæk&quot;</a></li>"
    )
    assert preflight._benign_removal(line, local_text="<p>new</p>", digest_text=evidence)
