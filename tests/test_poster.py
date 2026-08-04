"""Tests for poster.py — X API posting and threading."""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import tweepy  # noqa: E402
import src.bot.poster as poster  # noqa: E402


class TestPostTweetDryRun:
    def test_returns_dry_run_string(self):
        poster.DRY_RUN = True
        result = poster.post_tweet("Test tweet")
        assert result == "dry-run"

    def test_returns_dry_run_with_reply(self):
        poster.DRY_RUN = True
        result = poster.post_tweet("Reply text", reply_to="123456")
        assert result == "dry-run"

    def test_does_not_call_client(self):
        poster.DRY_RUN = True
        with mock.patch("src.bot.poster._get_client") as mock_client:
            result = poster.post_tweet("Test")
            assert result == "dry-run"
            mock_client.assert_not_called()


class TestPostTweetLiveMode:
    def test_posts_tweet_successfully(self):
        poster.DRY_RUN = False
        with mock.patch("src.bot.poster._get_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.return_value.data = {"id": "998877"}
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Hello world")
            assert result == "998877"
            mock_client.create_tweet.assert_called_once_with(text="Hello world")

    def test_posts_reply_with_in_reply_to(self):
        poster.DRY_RUN = False
        with mock.patch("src.bot.poster._get_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.return_value.data = {"id": "555"}
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Reply", reply_to="123")
            assert result == "555"
            mock_client.create_tweet.assert_called_once_with(
                text="Reply", in_reply_to_tweet_id="123"
            )

    def test_handles_tweepy_error(self):
        poster.DRY_RUN = False
        with mock.patch("src.bot.poster._get_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = tweepy.TweepyException(
                "API error"
            )
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Fail")
            assert result is None

    def test_handles_forbidden(self):
        poster.DRY_RUN = False
        with mock.patch("src.bot.poster._get_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = tweepy.Forbidden(
                response=mock.MagicMock()
            )
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Forbidden")
            assert result is None

    def test_retries_on_rate_limit(self):
        poster.DRY_RUN = False
        with (
            mock.patch("src.bot.poster._get_client") as mock_get_client,
            mock.patch("src.bot.poster.time.sleep") as mock_sleep,
        ):
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = [
                tweepy.TooManyRequests(response=mock.MagicMock()),
                mock.MagicMock(data={"id": "retry-ok"}),
            ]
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Rate limited")
            assert result == "retry-ok"
            assert mock_client.create_tweet.call_count == 2
            mock_sleep.assert_called_once()

    def test_rate_limit_retry_fails(self):
        poster.DRY_RUN = False
        with (
            mock.patch("src.bot.poster._get_client") as mock_get_client,
            mock.patch("src.bot.poster.time.sleep") as mock_sleep,
        ):
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = [
                tweepy.TooManyRequests(response=mock.MagicMock()),
                tweepy.TweepyException("Still failing"),
            ]
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Rate limited then fail")
            assert result is None
            assert mock_client.create_tweet.call_count == 2

    def test_get_client_missing_credentials(self):
        poster.DRY_RUN = False
        with mock.patch.object(poster, "X_API_KEY", ""):
            with pytest.raises(RuntimeError, match="credentials"):
                poster._get_client()

    def test_get_client_success_with_keys(self):
        """With fake keys set in conftest, _get_client constructs a tweepy Client."""
        client = poster._get_client()
        assert client is not None


class TestPostThread:
    def test_empty_list_returns_empty(self):
        result = poster.post_thread([])
        assert result == []

    def test_returns_dry_run_for_all(self):
        poster.DRY_RUN = True
        texts = ["Tweet 1", "Tweet 2", "Tweet 3"]
        result = poster.post_thread(texts)
        assert result == ["dry-run", "dry-run", "dry-run"]
        assert len(result) == 3

    def test_threads_chain_replies(self):
        poster.DRY_RUN = False
        with mock.patch("src.bot.poster._get_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = [
                mock.MagicMock(data={"id": "111"}),
                mock.MagicMock(data={"id": "222"}),
                mock.MagicMock(data={"id": "333"}),
            ]
            mock_get_client.return_value = mock_client

            result = poster.post_thread(["First", "Second", "Third"])
            assert result == ["111", "222", "333"]

            # Second call should be reply to "111"
            call_args_list = mock_client.create_tweet.call_args_list
            assert "in_reply_to_tweet_id" not in call_args_list[0][1]
            assert call_args_list[1][1]["in_reply_to_tweet_id"] == "111"
            assert call_args_list[2][1]["in_reply_to_tweet_id"] == "222"
