"""Shareability gate for the published site.

Every page we publish — the landing page, the archive index and the weekly digest
archives — is meant to be shared on Reddit, Facebook and X. A shared link whose
card is missing (or whose image is missing/relative) renders as a bare URL and
loses clicks, which is exactly the wrong direction for a distribution-first plan.

This test fails CI if any published page drops its Open Graph / Twitter card
metadata, if a card URL is relative (crawlers require absolute URLs) or points at
a file that does not exist, or if the card image is not a 1200x630 PNG.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest

from src.digest import publisher

REPO_ROOT = Path(__file__).resolve().parent.parent
WEBSITE = REPO_ROOT / "website"
BASE_URL = publisher.SITE_BASE_URL

REQUIRED_META = (
    "og:type",
    "og:title",
    "og:description",
    "og:url",
    "og:image",
    "og:image:width",
    "og:image:height",
    "twitter:card",
    "twitter:title",
    "twitter:image",
)
ABSOLUTE_META = ("og:url", "og:image", "twitter:image")


def _pages() -> list[Path]:
    return sorted(WEBSITE.rglob("*.html"))


def _meta(html_text: str, name: str) -> str | None:
    match = re.search(
        rf'<meta (?:property|name)="{re.escape(name)}" content="([^"]*)"', html_text
    )
    return match.group(1) if match else None


@pytest.mark.parametrize("page", _pages(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_page_has_share_metadata(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    missing = [tag for tag in REQUIRED_META if not _meta(text, tag)]
    assert missing == [], f"{page.relative_to(REPO_ROOT)} is missing {missing}"


@pytest.mark.parametrize("page", _pages(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_share_urls_are_absolute_and_the_image_exists(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    for tag in ABSOLUTE_META:
        value = _meta(text, tag)
        assert value is not None, f"{page.relative_to(REPO_ROOT)}: {tag} missing"
        assert value.startswith("https://"), (
            f"{page.relative_to(REPO_ROOT)}: {tag}={value!r} must be an absolute URL"
        )

    image = _meta(text, "og:image")
    assert image is not None
    assert image.startswith(f"{BASE_URL}/"), (
        f"{page.relative_to(REPO_ROOT)}: og:image={image!r} must live on the site root"
    )
    local_path = WEBSITE / image[len(BASE_URL) + 1 :]
    assert local_path.is_file(), f"og:image points at a missing asset: {local_path}"


def test_card_is_a_1200x630_png() -> None:
    data = (WEBSITE / "og-image.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "og-image.png is not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (1200, 630)


def test_landing_page_uses_the_large_card() -> None:
    text = (WEBSITE / "index.html").read_text(encoding="utf-8")
    assert _meta(text, "twitter:card") == "summary_large_image"


def test_digest_archive_template_keeps_share_metadata() -> None:
    digest = {"week": 33, "year": 2026, "total_posts": 105, "categories": {}}
    html_text = publisher._render_archive_html(digest)

    assert _meta(html_text, "og:url") == f"{BASE_URL}/uge/2026/33/"
    assert _meta(html_text, "og:image") == f"{BASE_URL}/og-image.png"
    assert _meta(html_text, "twitter:card") == "summary_large_image"
    assert _meta(html_text, "twitter:image") == f"{BASE_URL}/og-image.png"
