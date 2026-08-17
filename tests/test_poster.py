"""Tests for poster.py — X API posting and threading."""

import os
import sys
import json
import tempfile
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import tweepy  # noqa: E402
import src.bot.poster as poster  # noqa: E402


class TestPostTweetLiveMode:
    def test_posts_tweet_successfully(self):
        with mock.patch("src.bot.poster._get_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.return_value.data = {"id": "998877"}
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Hello world")
            assert result == "998877"
            mock_client.create_tweet.assert_called_once_with(text="Hello world")

    def test_posts_reply_with_in_reply_to(self):
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
        with mock.patch("src.bot.poster._get_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = tweepy.TweepyException(
                "API error"
            )
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Fail")
            assert result is None

    def test_handles_forbidden(self):
        with mock.patch("src.bot.poster._get_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_client.create_tweet.side_effect = tweepy.Forbidden(
                response=mock.MagicMock()
            )
            mock_get_client.return_value = mock_client

            result = poster.post_tweet("Forbidden")
            assert result is None

    def test_retries_on_rate_limit(self):
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
        with (
            mock.patch.object(poster, "X_API_KEY", ""),
            mock.patch.object(poster, "X_CLIENT_ID", ""),
        ):
            with pytest.raises(RuntimeError, match="credentials"):
                poster._get_client()

    def test_get_client_oauth1_success(self):
        client = poster._get_client()
        assert client is not None

    def test_get_client_oauth1_missing_key(self):
        with mock.patch.object(poster, "X_API_KEY", ""):
            with pytest.raises(RuntimeError, match="configured"):
                poster._get_client_oauth1()

    def test_get_client_oauth2_success_with_valid_token(self):
        with (
            mock.patch.object(poster, "X_ACCESS_TOKEN", ""),
            mock.patch.object(poster, "_load_tokens", return_value={
                "access_token": "fake-access-token",
                "refresh_token": "fake-refresh-token",
                "expires_in": 7200,
                "obtained_at": int(time.time())
            }),
        ):
            client = poster._get_client()
            assert client is not None

    def test_get_client_oauth2_refreshes_expired_token(self):
        with (
            mock.patch.object(poster, "X_ACCESS_TOKEN", ""),
            mock.patch.object(poster, "_load_tokens", return_value={
                "access_token": "expired-token",
                "refresh_token": "fake-refresh-token",
                "expires_in": 7200,
                "obtained_at": 0
            }),
        ):
            with mock.patch.object(poster, "_refresh_access_token", return_value={
                "access_token": "fresh-token",
                "refresh_token": "fake-refresh-token",
                "expires_in": 7200,
                "obtained_at": int(time.time())
            }) as mock_refresh:
                with mock.patch.object(poster, "_save_tokens") as mock_save:
                    client = poster._get_client()
                    assert client is not None
                    mock_refresh.assert_called_once()
                    mock_save.assert_called_once()

    def test_load_tokens_raises_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = os.path.join(tmpdir, "nonexistent.json")
            with mock.patch.object(poster, "X_TOKEN_FILE", token_path):
                with pytest.raises(RuntimeError, match="token file not found"):
                    poster._load_tokens()

    def test_load_tokens_reads_valid_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = os.path.join(tmpdir, "tokens.json")
            expected = {"access_token": "abc", "refresh_token": "xyz"}
            with open(token_path, "w") as f:
                json.dump(expected, f)
            with mock.patch.object(poster, "X_TOKEN_FILE", token_path):
                result = poster._load_tokens()
                assert result == expected

    def test_save_tokens_creates_parent_dirs_and_writes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            token_path = os.path.join(tmpdir, "subdir", "tokens.json")
            tokens = {"access_token": "abc", "refresh_token": "xyz"}
            with mock.patch.object(poster, "X_TOKEN_FILE", token_path):
                poster._save_tokens(tokens)
            assert os.path.exists(token_path)
            with open(token_path) as f:
                assert json.load(f) == tokens

    def test_refresh_access_token_calls_tweepy(self):
        with mock.patch("tweepy.OAuth2UserHandler") as mock_handler_class:
            mock_handler = mock.MagicMock()
            mock_handler.refresh_token.return_value = {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 7200,
            }
            mock_handler_class.return_value = mock_handler

            result = poster._refresh_access_token("old-refresh")
            assert result["access_token"] == "new-access"
            assert result["refresh_token"] == "new-refresh"
            assert "obtained_at" in result
            mock_handler.refresh_token.assert_called_once_with(
                "https://api.x.com/2/oauth2/token", refresh_token="old-refresh"
            )

    def test_get_tokens_from_env_var_when_no_file_exists(self, tmp_path):
        token_path = tmp_path / "does-not-exist.json"
        fresh_tokens = {"access_token": "env-token", "refresh_token": "env-refresh", "expires_in": 7200, "obtained_at": int(time.time())}
        with mock.patch.object(poster, "X_TOKEN_FILE", str(token_path)):
            with mock.patch.object(poster, "X_REFRESH_TOKEN", "env-refresh-token"):
                with mock.patch.object(poster, "_refresh_access_token", return_value=fresh_tokens) as mock_refresh:
                    with mock.patch.object(poster, "_save_tokens") as mock_save:
                        result = poster._get_tokens()
                        assert result == fresh_tokens
                        mock_refresh.assert_called_once_with("env-refresh-token")
                        mock_save.assert_called_once_with(fresh_tokens)

    def test_get_tokens_from_file_when_no_env_var(self, tmp_path):
        token_path = tmp_path / "does-not-exist.json"
        expected = {"access_token": "file-token", "refresh_token": "file-refresh"}
        with mock.patch.object(poster, "X_TOKEN_FILE", str(token_path)):
            with mock.patch.object(poster, "X_REFRESH_TOKEN", ""):
                with mock.patch.object(poster, "_load_tokens", return_value=expected) as mock_load:
                    result = poster._get_tokens()
                    assert result == expected
                    mock_load.assert_called_once()

    def test_prefers_existing_file_over_stale_env_refresh_token(self, tmp_path):
        """A static X_REFRESH_TOKEN is single-use (X rotates on every refresh) —
        once a token file exists, it must win, or every run after the first
        would try to reuse an already-consumed refresh token."""
        token_path = tmp_path / "tokens.json"
        token_path.write_text(json.dumps({"access_token": "from-file", "refresh_token": "file-rtok"}))
        with mock.patch.object(poster, "X_TOKEN_FILE", str(token_path)):
            with mock.patch.object(poster, "X_REFRESH_TOKEN", "stale-env-rtok"):
                with mock.patch.object(poster, "_refresh_access_token") as mock_refresh:
                    result = poster._get_tokens()

        assert result["access_token"] == "from-file"
        mock_refresh.assert_not_called()


class TestPostThread:
    def test_empty_list_returns_empty(self):
        result = poster.post_thread([])
        assert result == []

    def test_threads_chain_replies(self):
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
