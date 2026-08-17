"""Tests for the digest state guard and duplicate-content handling.

Covers the per-week idempotency fix: weekly-post was re-firing (e.g. a
misfiring schedule) and hitting X's duplicate-content 403 every time,
since the tweet text is fully determined by week/total/categories/url.
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import tweepy  # noqa: E402

import src.digest.main as digest_main  # noqa: E402
import src.digest.poster as poster  # noqa: E402
import src.digest.state as state  # noqa: E402


class TestState:
    def test_read_missing_file_returns_empty(self, tmp_path):
        with mock.patch.object(state.config, "DIGEST_STATE_PATH", str(tmp_path / "missing.json")):
            assert state.read() == {}

    def test_write_creates_parent_dirs_and_persists(self, tmp_path):
        state_path = tmp_path / "sub" / "digest_state.json"
        with mock.patch.object(state.config, "DIGEST_STATE_PATH", str(state_path)):
            state.write({"last_posted_week": "2026-W33"})
            assert state.read() == {"last_posted_week": "2026-W33"}

    def test_write_merges_into_existing_state(self, tmp_path):
        state_path = tmp_path / "digest_state.json"
        with mock.patch.object(state.config, "DIGEST_STATE_PATH", str(state_path)):
            state.write({"last_posted_week": "2026-W32"})
            state.write({"last_posted_week": "2026-W33"})
            assert state.read() == {"last_posted_week": "2026-W33"}


class TestRunSkipsAlreadyPostedWeek:
    def test_skips_when_state_matches_current_week(self):
        with mock.patch.object(digest_main.state, "read", return_value={"last_posted_week": "2026-W33"}):
            with mock.patch.object(digest_main.builder, "build") as mock_build:
                digest_main.run(week=33, year=2026, dry_run=False, skip_tweet=False)
                mock_build.assert_not_called()

    def test_runs_when_state_is_for_a_different_week(self):
        with mock.patch.object(digest_main.state, "read", return_value={"last_posted_week": "2026-W32"}):
            with mock.patch.object(
                digest_main.builder, "build",
                return_value={"total_posts": 0, "categories": {}, "posts_by_category": {}},
            ) as mock_build:
                digest_main.run(week=33, year=2026, dry_run=False, skip_tweet=False)
                mock_build.assert_called_once_with(2026, 33)

    def test_dry_run_ignores_state(self):
        with mock.patch.object(digest_main.state, "read", return_value={"last_posted_week": "2026-W33"}):
            with mock.patch.object(
                digest_main.builder, "build",
                return_value={"total_posts": 0, "categories": {}, "posts_by_category": {}},
            ) as mock_build:
                digest_main.run(week=33, year=2026, dry_run=True, skip_tweet=False)
                mock_build.assert_called_once()

    def test_successful_run_writes_state(self):
        data = {
            "total_posts": 5,
            "categories": {"other": 5},
            "posts_by_category": {},
        }
        generate_result = {"narrative": "narrative", "narrative_html": "narrative", "notable": []}
        with mock.patch.object(digest_main.state, "read", return_value={}):
            with mock.patch.object(digest_main.builder, "build", return_value=data):
                with mock.patch.object(digest_main.generator, "generate", return_value=generate_result):
                    with mock.patch.object(digest_main.gist, "publish", return_value="https://gist/raw"):
                        with mock.patch.object(digest_main.publisher, "commit_archive"):
                            with mock.patch.object(digest_main.poster, "post_tweet", return_value="12345"):
                                with mock.patch.object(digest_main.state, "write") as mock_write:
                                    digest_main.run(week=33, year=2026, dry_run=False, skip_tweet=False)
                                    mock_write.assert_called_once_with({"last_posted_week": "2026-W33"})

    def test_no_posts_does_not_write_state(self):
        data = {"total_posts": 0, "categories": {}, "posts_by_category": {}}
        with mock.patch.object(digest_main.state, "read", return_value={}):
            with mock.patch.object(digest_main.builder, "build", return_value=data):
                with mock.patch.object(digest_main.state, "write") as mock_write:
                    digest_main.run(week=33, year=2026, dry_run=False, skip_tweet=False)
                    mock_write.assert_not_called()


class TestPostTweetDuplicateContent:
    @staticmethod
    def _forbidden(message: str) -> tweepy.errors.Forbidden:
        exc = tweepy.errors.Forbidden.__new__(tweepy.errors.Forbidden)
        exc.api_messages = [message]
        return exc

    def test_duplicate_content_is_treated_as_already_posted(self):
        digest = {"week": 33, "year": 2026, "total_posts": 5, "categories": {}}
        with mock.patch("src.digest.poster.tweepy.Client") as mock_client_cls:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = self._forbidden(
                "You are not allowed to create a Tweet with duplicate content."
            )
            mock_client_cls.return_value = mock_client

            result = poster.post_tweet(digest, "https://politiupdate.dk/uge/2026/33")
            assert result is None

    def test_other_forbidden_reason_still_raises(self):
        digest = {"week": 33, "year": 2026, "total_posts": 5, "categories": {}}
        with mock.patch("src.digest.poster.tweepy.Client") as mock_client_cls:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = self._forbidden("Account is suspended.")
            mock_client_cls.return_value = mock_client

            with pytest.raises(tweepy.errors.Forbidden):
                poster.post_tweet(digest, "https://politiupdate.dk/uge/2026/33")
