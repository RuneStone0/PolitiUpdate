"""Tests for the monthly feedback-request module.

Covers the per-month idempotency guard (mirrors src/digest's per-week guard)
and duplicate-content handling for X posting.
"""

import os
import sys
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import tweepy  # noqa: E402

import src.feedback.main as feedback_main  # noqa: E402
import src.feedback.poster as poster  # noqa: E402
import src.feedback.state as state  # noqa: E402


class TestState:
    def test_read_missing_file_returns_empty(self, tmp_path):
        with mock.patch.object(state.config, "FEEDBACK_STATE_PATH", str(tmp_path / "missing.json")):
            assert state.read() == {}

    def test_write_creates_parent_dirs_and_persists(self, tmp_path):
        state_path = tmp_path / "sub" / "feedback_state.json"
        with mock.patch.object(state.config, "FEEDBACK_STATE_PATH", str(state_path)):
            state.write({"last_posted_month": "2026-08"})
            assert state.read() == {"last_posted_month": "2026-08"}

    def test_write_merges_into_existing_state(self, tmp_path):
        state_path = tmp_path / "feedback_state.json"
        with mock.patch.object(state.config, "FEEDBACK_STATE_PATH", str(state_path)):
            state.write({"last_posted_month": "2026-07"})
            state.write({"last_posted_month": "2026-08"})
            assert state.read() == {"last_posted_month": "2026-08"}


class TestRunSkipsAlreadyPostedMonth:
    def test_skips_when_state_matches_current_month(self):
        with mock.patch.object(feedback_main.state, "read", return_value={"last_posted_month": "2026-08"}):
            with mock.patch.object(feedback_main.poster, "post_tweet") as mock_post:
                feedback_main.run(year=2026, month=8, dry_run=False)
                mock_post.assert_not_called()

    def test_runs_when_state_is_for_a_different_month(self):
        with mock.patch.object(feedback_main.state, "read", return_value={"last_posted_month": "2026-07"}):
            with mock.patch.object(feedback_main.poster, "post_tweet", return_value="12345") as mock_post:
                with mock.patch.object(feedback_main.state, "write") as mock_write:
                    feedback_main.run(year=2026, month=8, dry_run=False)
                    mock_post.assert_called_once_with(2026, 8, dry_run=False)
                    mock_write.assert_called_once_with({"last_posted_month": "2026-08"})

    def test_dry_run_ignores_state_and_skips_state_write(self):
        with mock.patch.object(feedback_main.state, "read", return_value={"last_posted_month": "2026-08"}):
            with mock.patch.object(feedback_main.poster, "post_tweet", return_value=None) as mock_post:
                with mock.patch.object(feedback_main.state, "write") as mock_write:
                    feedback_main.run(year=2026, month=8, dry_run=True)
                    mock_post.assert_called_once_with(2026, 8, dry_run=True)
                    mock_write.assert_not_called()

    def test_successful_run_writes_state_even_on_duplicate_content(self):
        # post_tweet returns None when X treats a re-run as a duplicate —
        # the month is still considered done, matching src/digest's behavior.
        with mock.patch.object(feedback_main.state, "read", return_value={}):
            with mock.patch.object(feedback_main.poster, "post_tweet", return_value=None):
                with mock.patch.object(feedback_main.state, "write") as mock_write:
                    feedback_main.run(year=2026, month=8, dry_run=False)
                    mock_write.assert_called_once_with({"last_posted_month": "2026-08"})


class TestMainArgParsing:
    def test_month_flag_overrides_default(self):
        with mock.patch.object(feedback_main, "run") as mock_run:
            feedback_main.main(["--month", "2026-08"])
            mock_run.assert_called_once_with(2026, 8, dry_run=False)

    def test_config_override_used_when_no_flag(self):
        with mock.patch.object(feedback_main.config, "FEEDBACK_MONTH_OVERRIDE", "2026-03"):
            with mock.patch.object(feedback_main, "run") as mock_run:
                feedback_main.main([])
                mock_run.assert_called_once_with(2026, 3, dry_run=False)


class TestSchedulingGate:
    # 2026-08-01 is a Saturday (the first of the month); 2026-08-08 is the
    # second Saturday; 2026-08-03 is a Monday.
    def test_first_saturday_before_hour_is_not_scheduled(self):
        now = datetime(2026, 8, 1, 17, 59)
        assert feedback_main._is_first_saturday_at_or_after_hour(now, 18) is False

    def test_first_saturday_at_hour_is_scheduled(self):
        now = datetime(2026, 8, 1, 18, 0)
        assert feedback_main._is_first_saturday_at_or_after_hour(now, 18) is True

    def test_first_saturday_after_hour_is_scheduled(self):
        now = datetime(2026, 8, 1, 23, 0)
        assert feedback_main._is_first_saturday_at_or_after_hour(now, 18) is True

    def test_second_saturday_is_not_scheduled(self):
        now = datetime(2026, 8, 8, 19, 0)
        assert feedback_main._is_first_saturday_at_or_after_hour(now, 18) is False

    def test_non_saturday_is_not_scheduled(self):
        now = datetime(2026, 8, 3, 19, 0)
        assert feedback_main._is_first_saturday_at_or_after_hour(now, 18) is False

    def test_main_skips_run_when_not_scheduled_time(self):
        with mock.patch.object(feedback_main, "_now_local", return_value=datetime(2026, 8, 3, 19, 0)):
            with mock.patch.object(feedback_main, "run") as mock_run:
                feedback_main.main([])
                mock_run.assert_not_called()

    def test_main_runs_when_scheduled_time(self):
        with mock.patch.object(feedback_main, "_now_local", return_value=datetime(2026, 8, 1, 18, 0)):
            with mock.patch.object(feedback_main, "run") as mock_run:
                feedback_main.main([])
                mock_run.assert_called_once_with(2026, 8, dry_run=False)

    def test_force_flag_bypasses_gate(self):
        with mock.patch.object(feedback_main, "_now_local", return_value=datetime(2026, 8, 3, 19, 0)):
            with mock.patch.object(feedback_main, "run") as mock_run:
                feedback_main.main(["--force"])
                mock_run.assert_called_once_with(2026, 8, dry_run=False)

    def test_dry_run_bypasses_gate(self):
        with mock.patch.object(feedback_main, "_now_local", return_value=datetime(2026, 8, 3, 19, 0)):
            with mock.patch.object(feedback_main, "run") as mock_run:
                feedback_main.main(["--dry-run"])
                mock_run.assert_called_once_with(2026, 8, dry_run=True)

    def test_explicit_month_bypasses_gate(self):
        with mock.patch.object(feedback_main, "_now_local", return_value=datetime(2026, 8, 3, 19, 0)):
            with mock.patch.object(feedback_main, "run") as mock_run:
                feedback_main.main(["--month", "2026-09"])
                mock_run.assert_called_once_with(2026, 9, dry_run=False)


class TestPostTweetDuplicateContent:
    @staticmethod
    def _forbidden(message: str) -> tweepy.errors.Forbidden:
        exc = tweepy.errors.Forbidden.__new__(tweepy.errors.Forbidden)
        exc.api_messages = [message]
        return exc

    def test_duplicate_content_is_treated_as_already_posted(self):
        with mock.patch("src.feedback.poster.tweepy.Client") as mock_client_cls:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = self._forbidden(
                "You are not allowed to create a Tweet with duplicate content."
            )
            mock_client_cls.return_value = mock_client

            result = poster.post_tweet(2026, 8)
            assert result is None

    def test_other_forbidden_reason_still_raises(self):
        with mock.patch("src.feedback.poster.tweepy.Client") as mock_client_cls:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = self._forbidden("Account is suspended.")
            mock_client_cls.return_value = mock_client

            with pytest.raises(tweepy.errors.Forbidden):
                poster.post_tweet(2026, 8)

    def test_dry_run_does_not_call_api(self):
        with mock.patch("src.feedback.poster.tweepy.Client") as mock_client_cls:
            result = poster.post_tweet(2026, 8, dry_run=True)
            assert result is None
            mock_client_cls.assert_not_called()

    def test_missing_credentials_raises(self):
        with mock.patch.object(poster.config, "X_API_KEY", ""):
            with pytest.raises(RuntimeError):
                poster.post_tweet(2026, 8)

    def test_successful_post_returns_tweet_id(self):
        with mock.patch("src.feedback.poster.tweepy.Client") as mock_client_cls:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.return_value = mock.Mock(data={"id": "999"})
            mock_client_cls.return_value = mock_client

            result = poster.post_tweet(2026, 8)
            assert result == "999"

    def test_build_tweet_includes_danish_month_and_year(self):
        text = poster._build_tweet(2026, 8)
        assert "august" in text
        assert "2026" in text
        assert len(text) <= 280
