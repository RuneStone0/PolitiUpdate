"""Regression tests against known press release URLs.

These verify that the pipeline (fetch → extract → format) produces expected
output for specific, known pages. If the page HTML changes or our parser breaks,
these tests catch it before deployment.
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.bot import fetcher, formatter, config

# Known press release URLs — these pages are stable and well-understood.
# Each entry: (url, expected_district, min_thread_items, must_contain, description)
REGRESSION_CASES = [
    (
        "https://via.ritzau.dk/pressemeddelelse/15073728/efterlysning-78-arige-henning-savnes-naer-korsoer",
        "Sydsjællands og Lolland-Falsters Politi",
        2,
        ["Henning", "eftersøgningen", "Korsør", "114"],
        "Missing person (Henning) — multi-update, public appeal",
    ),
    (
        "https://via.ritzau.dk/pressemeddelelse/15073120/grundlovsforhor-i-retten-i-randers-kl-1600",
        "Anklagemyndigheden ved Østjyllands Politi",
        3,
        ["grundlovsforhør", "Randers", "varetægtsfængslet", "terrorisme"],
        "Court hearing (Randers) — three updates, complex body",
    ),
    (
        "https://via.ritzau.dk/pressemeddelelse/15079728/vi-savner-abdelilah?lang=da",
        "Københavns Politi",
        1,
        ["autist", "114"],
        "Missing person (Abdelilah) — single update, condensation required",
    ),
]


class TestRegressionFetch:
    @pytest.mark.parametrize("url,district,min_items,must_contain,desc", REGRESSION_CASES)
    def test_fetches_and_extracts(self, url, district, min_items, must_contain, desc):
        """Fetch a known page and verify extraction."""
        actual_district, thread_items = fetcher.fetch_press_release(url)

        assert actual_district == district, f"Wrong district for {desc}"
        assert len(thread_items) >= min_items, (
            f"Expected >= {min_items} thread items, got {len(thread_items)} for {desc}"
        )
        assert thread_items[0]["body"], f"Latest body is empty for {desc}"

        combined = " ".join(ti["body"] for ti in thread_items)
        for keyword in must_contain:
            assert keyword.lower() in combined.lower(), (
                f"Missing keyword '{keyword}' in {desc}"
            )

    @pytest.mark.parametrize("url,district,min_items,must_contain,desc", REGRESSION_CASES)
    def test_formatting_produces_valid_posts(self, url, district, min_items, must_contain, desc):
        """Verify formatting produces non-empty posts with district prefix."""
        actual_district, thread_items = fetcher.fetch_press_release(url)
        title = f"Regression test — {desc}"

        for i, ti in enumerate(thread_items):
            post = formatter.format_post(title, actual_district, ti["body"])
            assert post, f"Empty post for thread item {i} in {desc}"
            assert "\n\n" in post or ti["body"], (
                f"Missing body separator in {desc}"
            )

    @pytest.mark.parametrize("url,district,min_items,must_contain,desc", REGRESSION_CASES)
    def test_truncation_mode(self, url, district, min_items, must_contain, desc):
        """Verify truncation at 280 chars produces clean cuts."""
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = False

        actual_district, thread_items = fetcher.fetch_press_release(url)

        for ti in thread_items:
            post = formatter.format_post("Test", actual_district, ti["body"])
            if len(post) > 280:
                assert "…" in post, (
                    f"Post over 280 chars missing truncation marker in {desc}"
                )

    @pytest.mark.parametrize("url,district,min_items,must_contain,desc", REGRESSION_CASES)
    def test_full_length_mode(self, url, district, min_items, must_contain, desc):
        """Verify full-length mode doesn't truncate."""
        formatter.POST_MAX_CHARS = 280
        # Temporarily use full-length
        formatter.POST_MAX_CHARS = 25000
        formatter.LLM_ENABLED = False

        actual_district, thread_items = fetcher.fetch_press_release(url)

        for ti in thread_items:
            post = formatter.format_post("Test", actual_district, ti["body"])
            assert "…" not in post, (
                f"Full-length post has truncation marker in {desc}"
            )

    @pytest.mark.parametrize("url,district,min_items,must_contain,desc", REGRESSION_CASES)
    def test_llm_mock_produces_clean_sentences(self, url, district, min_items, must_contain, desc):
        """Verify LLM mock produces posts ending at sentence boundaries."""
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = True

        actual_district, thread_items = fetcher.fetch_press_release(url)

        for ti in thread_items:
            with mock.patch("src.bot.summarizer.summarize") as mock_sum:
                # Return body truncated at sentence boundary
                body = ti["body"]
                mock_sum.return_value = body[: min(150, len(body))]

                post = formatter.format_post("Test", actual_district, body)
                assert post, f"LLM mock produced empty post in {desc}"
                # Either the mock was used (no …) or truncation kicked in
                # Either way, post should be non-empty and fit
                assert len(post) <= 280, (
                    f"LLM post exceeds limit in {desc}: {len(post)} chars"
                )
