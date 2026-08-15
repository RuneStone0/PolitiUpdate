"""Tests for formatter.py — post formatting, truncation, LLM condensation."""

import src.bot.formatter as formatter
import src.bot.config as config


class TestDistrictPrefix:
    def test_maps_known_districts(self):
        cases = [
            ("Bornholms Politi", "Bornholm"),
            ("Fyns Politi", "Fyn"),
            ("Københavns Politi", "København"),
            ("Københavns Vestegns Politi", "Kbh Vestegn"),
            ("Midt- og Vestjyllands Politi", "Midt/Vestjylland"),
            ("Midt- og Vestsjællands Politi", "Midt/Vestsjælland"),
            ("National enhed for Særlig Kriminalitet", "NSK"),
            ("Nordjyllands Politi", "Nordjylland"),
            ("Nordsjællands Politi", "Nordsjælland"),
            ("Syd- og Sønderjyllands Politi", "Sydjylland"),
            ("Sydøstjyllands Politi", "Sydøstjylland"),
            ("Sydsjællands og Lolland-Falsters Politi", "Sydsjælland/L-F"),
            ("Østjyllands Politi", "Østjylland"),
            ("Rigspolitiet", "Rigspolitiet"),
        ]
        for full, expected in cases:
            assert formatter._district_prefix(full) == expected

    def test_returns_empty_for_empty_string(self):
        assert formatter._district_prefix("") == ""

    def test_fallback_takes_first_part_before_comma(self):
        result = formatter._district_prefix("Ukendt, og mere, Politi")
        assert result == "Ukendt"

    def test_fallback_strips_og(self):
        result = formatter._district_prefix("X og Y Politi")
        assert result == "X"


class TestTruncate:
    def test_does_not_truncate_short_text(self):
        result = formatter._truncate("Kort besked.", 280)
        assert result == "Kort besked."
        assert "…" not in result

    def test_truncates_at_sentence_boundary(self):
        text = "Første sætning. Anden sætning der er meget lang og fylder meget mere plads."
        result = formatter._truncate(text, 30)
        assert result.endswith("…")
        assert "Første sætning." in result
        assert len(result) <= 30

    def test_truncates_at_space_when_no_sentence_end(self):
        text = "enlangtekstudenmellemrum så kommer der mere tekst bagefter"
        result = formatter._truncate(text, 35)
        assert result.endswith("…")
        assert len(result) <= 35

    def test_truncates_at_char_limit_when_no_space(self):
        text = "enlangsammenhængendestrengudennogenmellemrum"
        result = formatter._truncate(text, 20)
        assert result.endswith("…")
        assert len(result) <= 20

    def test_handles_exclamation_mark_sentence_end(self):
        text = "Stop! Mere tekst følger efter her."
        result = formatter._truncate(text, 10)
        assert "Stop!" in result

    def test_handles_question_mark_sentence_end(self):
        text = "Er du sikker? Ja det er jeg."
        result = formatter._truncate(text, 20)
        assert "Er du sikker?" in result

    def test_exact_boundary_text_is_not_truncated(self):
        text = "Præcis 280 tegn lang tekst."
        result = formatter._truncate(text, 280)
        assert result == text


class TestFormatPost:
    def test_formats_with_district_and_body(self):
        formatter.POST_MAX_CHARS = 25000
        formatter.LLM_ENABLED = False
        result = formatter.format_post(
            "Test titel",
            "Sydsjællands og Lolland-Falsters Politi",
            "Dette er en test body.",
        )
        assert result.startswith("Sydsjælland/L-F: Test titel")
        assert "Dette er en test body." in result
        assert "\n\n" in result

    def test_formats_without_district(self):
        formatter.POST_MAX_CHARS = 25000
        result = formatter.format_post("Test titel", "", "Body tekst.")
        assert result.startswith("Test titel")
        assert ":" not in result.split("\n")[0]

    def test_formats_without_body(self):
        formatter.POST_MAX_CHARS = 25000
        result = formatter.format_post("Kun titel", "Nordjyllands Politi", "")
        assert result == "Nordjylland: Kun titel"
        assert "\n\n" not in result

    def test_truncates_when_exceeds_limit(self):
        formatter.POST_MAX_CHARS = 50
        formatter.LLM_ENABLED = False
        result = formatter.format_post(
            "Titel",
            "Bornholms Politi",
            "En meget lang body tekst der overstiger post max chars grænsen markant.",
        )
        assert result.endswith("…")
        assert len(result) <= 50

    def test_truncation_disabled_when_post_max_is_zero(self):
        formatter.POST_MAX_CHARS = 0
        formatter.LLM_ENABLED = False
        text = "En lang tekst " * 50
        result = formatter.format_post("T", "", text)
        assert result == f"T\n\n{text}"

    def test_no_truncation_when_post_fits_limit(self):
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = False
        result = formatter.format_post("Kort titel", "Fyns Politi", "Kort body.")
        assert "…" not in result
        assert "Kort body." in result

    def test_all_characters_in_result(self):
        """Verify truncation preserves complete content up to the cut point."""
        formatter.POST_MAX_CHARS = 100
        formatter.LLM_ENABLED = False
        body = "Sætning et. Sætning to som er længere."
        result = formatter.format_post("Titel", "Rigspolitiet", body)
        assert "Sætning et." in result
        # The truncated result should still contain meaningful content
        assert len(result) <= 100


    def test_truncates_when_sentence_end_at_boundary(self):
        text = "Aa." + "b" * 300
        result = formatter._truncate(text, 4)
        assert "Aa.…" in result


class TestCondenseOrTruncate:
    def test_falls_back_to_truncation_when_llm_disabled(self):
        formatter.POST_MAX_CHARS = 60
        formatter.LLM_ENABLED = False
        header = "Prefix: Titel"
        body = "Body tekst der er alt for lang til at passe ind i posten desværre og må derfor trunkeres."

        result = formatter._condense_or_truncate(
            f"{header}\n\n{body}", header, body
        )
        assert result.endswith("…")
        assert len(result) <= formatter.POST_MAX_CHARS

    def test_llm_exceeds_limit_falls_back_to_truncation(self):
        """When LLM returns text still too long, fall back to truncation."""
        formatter.POST_MAX_CHARS = 60
        formatter.LLM_ENABLED = True
        header = "X: Test"
        body = "A" * 500

        from unittest import mock

        with mock.patch("src.bot.summarizer.summarize") as mock_sum:
            mock_sum.return_value = "B" * 80  # longer than allowed
            result = formatter._condense_or_truncate(
                f"{header}\n\n{body}", header, body
            )
            assert result.endswith("…")
            assert len(result) <= formatter.POST_MAX_CHARS

    def test_llm_exception_falls_back_to_truncation(self):
        """When LLM raises, fall back to truncation."""
        formatter.POST_MAX_CHARS = 60
        formatter.LLM_ENABLED = True
        header = "X: Test"
        body = "C" * 500

        from unittest import mock

        with mock.patch("src.bot.summarizer.summarize") as mock_sum:
            mock_sum.side_effect = RuntimeError("API down")
            result = formatter._condense_or_truncate(
                f"{header}\n\n{body}", header, body
            )
            assert result.endswith("…")

    def test_llm_skipped_when_header_consumes_most_space(self):
        """When header overhead leaves <40 chars for body, skip LLM."""
        formatter.POST_MAX_CHARS = 50
        formatter.LLM_ENABLED = True
        header = "X" * 45  # only 3 chars left for body after overhead
        body = "D" * 500

        from unittest import mock

        with mock.patch("src.bot.summarizer.summarize") as mock_sum:
            result = formatter._condense_or_truncate(
                f"{header}\n\n{body}", header, body
            )
            mock_sum.assert_not_called()
            assert result.endswith("…")

    def test_llm_success_returns_condensed(self):
        """When LLM returns text within limit, it is used."""
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = True
        header = "Prefix: T"
        body = "E" * 500

        from unittest import mock

        with mock.patch("src.bot.summarizer.summarize") as mock_sum:
            mock_sum.return_value = "Kort kondenseret tekst."
            result = formatter._condense_or_truncate(
                f"{header}\n\n{body}", header, body
            )
            assert "Kort kondenseret tekst." in result
            assert "…" not in result

    def test_llm_retries_with_tighter_target_until_it_fits(self):
        """First condense attempt overshoots; retry with a tighter target
        should be tried before giving up and truncating."""
        formatter.POST_MAX_CHARS = 100
        formatter.LLM_ENABLED = True
        header = "X: Test"
        body = "F" * 500

        from unittest import mock

        with mock.patch("src.bot.summarizer.summarize") as mock_sum:
            mock_sum.side_effect = ["G" * 95, "Short fit."]
            result = formatter._condense_or_truncate(
                f"{header}\n\n{body}", header, body
            )
            assert result == f"{header}\n\nShort fit."
            assert mock_sum.call_count == 2
            # second call must ask for a tighter target than the first
            first_target = mock_sum.call_args_list[0][0][1]
            second_target = mock_sum.call_args_list[1][0][1]
            assert second_target < first_target

    def test_llm_gives_up_after_max_attempts_and_truncates(self):
        """If the LLM keeps overshooting past MAX_CONDENSE_ATTEMPTS, fall
        back to truncation rather than retrying forever."""
        formatter.POST_MAX_CHARS = 60
        formatter.LLM_ENABLED = True
        header = "X: Test"
        body = "H" * 500

        from unittest import mock

        with mock.patch("src.bot.summarizer.summarize") as mock_sum:
            mock_sum.return_value = "I" * 80  # always too long
            result = formatter._condense_or_truncate(
                f"{header}\n\n{body}", header, body
            )
            assert mock_sum.call_count == formatter.MAX_CONDENSE_ATTEMPTS
            assert result.endswith("…")
            assert len(result) <= formatter.POST_MAX_CHARS

    def test_llm_success_never_appends_sparkle(self):
        """Condensed posts must not get a trailing sparkle marker."""
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = True
        header = "Prefix: T"
        body = "E" * 500

        from unittest import mock

        with mock.patch("src.bot.summarizer.summarize") as mock_sum:
            mock_sum.return_value = "Kort kondenseret tekst."
            result = formatter._condense_or_truncate(
                f"{header}\n\n{body}", header, body
            )
            assert "✨" not in result

    def test_llm_result_never_exceeds_limit(self):
        """Full result (header + condensed) must never exceed the limit, even if LLM goes slightly over max_body_chars."""
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = True
        header = "København: Vi savner Abdelilah"
        body = "A" * 500

        from unittest import mock

        # LLM returns condensed body that is 5 chars over max_body_chars —
        # old code accepted this (+10 slack) and returned an over-limit post.
        header_overhead = len(header) + 2
        max_body_chars = 280 - header_overhead
        slightly_over = "B" * (max_body_chars + 5)

        with mock.patch("src.bot.summarizer.summarize") as mock_sum:
            mock_sum.return_value = slightly_over
            result = formatter._condense_or_truncate(
                f"{header}\n\n{body}", header, body
            )
            assert len(result) <= 280, f"result is {len(result)} chars, must be <= 280"


class TestRetweetPromptDetection:
    def test_detects_efterlysning(self):
        assert formatter._should_retweet_prompt(
            "Efterlysning: 78-årige Henning savnes. Kontakt politiet på 114."
        )

    def test_detects_savnet(self):
        assert formatter._should_retweet_prompt(
            "78-årig mand savnet i Korsør-området."
        )

    def test_detects_savner(self):
        assert formatter._should_retweet_prompt(
            "Vi savner Abdelilah som forsvandt fra en bustur."
        )

    def test_detects_ring_114(self):
        assert formatter._should_retweet_prompt(
            "Ring 114, hvis han træffes eller hvis man har oplysninger om, hvor han kan være."
        )

    def test_detects_man_har_oplysninger(self):
        assert formatter._should_retweet_prompt(
            "Kontakt politiet hvis man har oplysninger om hans færden."
        )

    def test_detects_eftersogning(self):
        assert formatter._should_retweet_prompt(
            "Tak for hjælpen med eftersøgningen."
        )

    def test_detects_kontakt_politiet(self):
        assert formatter._should_retweet_prompt(
            "Har du oplysninger, kontakt politiet på 114."
        )

    def test_detects_har_du_set(self):
        assert formatter._should_retweet_prompt(
            "Har du set Henning, kontakt politiet."
        )

    def test_detects_har_du_oplysninger(self):
        assert formatter._should_retweet_prompt(
            "Har du oplysninger om hvor han befinder sig."
        )

    def test_detects_bedes_du_kontakte(self):
        assert formatter._should_retweet_prompt(
            "Bedes du kontakte politiet på 114."
        )

    def test_does_not_match_regular_post(self):
        assert not formatter._should_retweet_prompt(
            "Grundlovsforhør i Retten i Randers kl. 16.00."
        )

    def test_does_not_match_empty_body(self):
        assert not formatter._should_retweet_prompt("")


class TestRetweetPromptSuffix:
    def test_appends_appeal_on_efterlysning(self):
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = False
        post = formatter.format_post(
            "Efterlysning: Mand savnet",
            "Sydsjællands og Lolland-Falsters Politi",
            "Har du set ham? Kontakt politiet på 114.",
        )
        assert "Del gerne 🔁" in post

    def test_does_not_append_on_regular_post(self):
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = False
        post = formatter.format_post(
            "Grundlovsforhør i dag",
            "Østjyllands Politi",
            "Anklagemyndigheden fremstiller tre personer.",
        )
        assert "Del gerne 🔁" not in post

    def test_retweet_prompt_survives_truncation(self):
        """Prompt always appears, space is reserved before truncation."""
        formatter.POST_MAX_CHARS = 50
        formatter.LLM_ENABLED = False
        body = "Har du set ham? Kontakt politiet på 114. Han er 78 år."
        post = formatter.format_post("T", "", body)
        assert "Del gerne 🔁" in post
        assert post.endswith("Del gerne 🔁")
        assert len(post) <= 50, f"post is {len(post)} chars, must be <= 50"

    def test_retweet_prompt_respects_280_limit(self):
        """Post with prompt must not exceed 280 chars (X API limit)."""
        formatter.POST_MAX_CHARS = 280
        formatter.LLM_ENABLED = False
        body = (
            "Har du set ham? "
            "Vi leder efter en 78-årig mand i Korsør-området. "
            "Kontakt politiet på 114 hvis du har oplysninger. "
            "Han beskrives som mand, dansk af udseende, 78 år, 175 cm, "
            "almindelig kropsbygning, gråt kort hår."
        )
        post = formatter.format_post("Efterlysning: Mand savnet", "Sydsjællands og Lolland-Falsters Politi", body)
        assert "Del gerne 🔁" in post
        assert len(post) <= 280, f"post is {len(post)} chars, must be <= 280"
