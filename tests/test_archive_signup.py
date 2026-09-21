"""The signup path must exist on every page a visitor can land on.

The weekly digest archives are the pages the digest tweet, the Reddit self-post
and the Facebook drafts all link to. Until this gate existed they carried **no
newsletter CTA and no form at all** (verified in the live week-37 HTML), so a
visitor arriving from the only off-platform reach we have could not subscribe
without navigating back to the landing page. That is a conversion hole in the
one channel that actually converts, and it was invisible because nothing tested
the published pages for a signup path.

These tests fail if:
  * the digest template stops rendering the signup block (future weeks regress);
  * a published archive page loses it again (i.e. a week page is published or
    re-rendered without the block) — run scripts/backfill-archive-pages.py;
  * the form on the landing page and the form in the template drift apart
    (Brevo has no Forms API; the markup is copied by hand and only the action
    URL identifies "our form");
  * the page stops loading Brevo's stylesheet/script (the panels and the inline
    submit handling come from there).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.digest import publisher

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE = REPO_ROOT / "website"

MINIMAL_DIGEST = {"week": 37, "year": 2026, "total_posts": 128, "categories": {}}


def _archive_pages() -> list[Path]:
    return sorted(WEBSITE.glob("uge/*/*/index.html"))


@pytest.mark.parametrize("page", _archive_pages(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_published_archive_page_offers_the_signup(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    assert 'class="digest-signup"' in text, (
        f"{page.relative_to(REPO_ROOT)} has no newsletter signup block — "
        "re-render it with scripts/backfill-archive-pages.py"
    )
    assert publisher.NEWSLETTER_FORM_ACTION in text, (
        f"{page.relative_to(REPO_ROOT)} does not post to our Brevo form"
    )
    assert re.search(r'name="EMAIL"', text), f"{page.relative_to(REPO_ROOT)}: no EMAIL input"


def test_digest_template_renders_the_signup_block() -> None:
    html_text = publisher._render_archive_html(MINIMAL_DIGEST)
    assert 'class="digest-signup"' in html_text
    assert publisher.NEWSLETTER_FORM_ACTION in html_text
    assert re.search(r'name="EMAIL"', html_text)


def test_template_loads_brevos_stylesheet_and_script() -> None:
    html_text = publisher._render_archive_html(MINIMAL_DIGEST)
    assert publisher.SIBFORMS_STYLESHEET in html_text
    assert publisher.SIBFORMS_SCRIPT in html_text


def test_landing_page_uses_the_same_form_as_the_archive_template() -> None:
    landing = (WEBSITE / "index.html").read_text(encoding="utf-8")
    assert publisher.NEWSLETTER_FORM_ACTION in landing, (
        "the landing page and the archive template must post to the same Brevo form — "
        "if the form was recreated in Brevo, update publisher.NEWSLETTER_FORM_ACTION too"
    )


def test_archive_index_uses_the_same_form() -> None:
    index = (WEBSITE / "uge" / "index.html").read_text(encoding="utf-8")
    assert publisher.NEWSLETTER_FORM_ACTION in index
    assert 'class="digest-signup"' in index


def test_signup_copy_does_not_promise_a_region_picker() -> None:
    """The live Brevo form is e-mail only, so the copy must say what a subscriber
    actually gets (everything, country-wide) instead of promising a choice that
    does not exist — the landing page carried exactly that false promise until
    2026-09-15."""
    block = publisher.render_signup_section()
    lowered = block.casefold()
    assert "vælg" not in lowered
    assert "region" not in lowered
    assert "hele danmark" in lowered
