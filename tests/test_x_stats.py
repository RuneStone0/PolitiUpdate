"""Tests for src.x_stats — X stats fetch, cache, and gist publish."""

import contextlib
import json
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import src.x_stats.gist as gist  # noqa: E402
import src.x_stats.main as main  # noqa: E402


def _user_data():
    class Data:
        username = "PolitiUpdate"
        public_metrics = {"tweet_count": 103, "followers_count": 1}

    return Data()


class TestFetchStats:
    def test_uses_get_me_and_writes_cache(self, tmp_path):
        with mock.patch.object(main, "_get_client") as mock_client:
            with mock.patch.object(main, "STATS_PATH", tmp_path / "x-stats.json"):
                response = mock.MagicMock()
                response.data = _user_data()
                mock_client.return_value.get_me.return_value = response

                stats = main.fetch_stats(force_refresh=True)

                assert stats["username"] == "PolitiUpdate"
                assert stats["tweet_count"] == 103
                assert stats["followers_count"] == 1
                mock_client.return_value.get_me.assert_called_once_with(
                    user_fields=["public_metrics"]
                )
                assert (tmp_path / "x-stats.json").exists()
                cached = json.loads((tmp_path / "x-stats.json").read_text())
                assert cached["tweet_count"] == 103

    def test_uses_cache_when_fresh(self, tmp_path):
        cache = tmp_path / "x-stats.json"
        cache.write_text(json.dumps({"tweet_count": 50, "username": "PolitiUpdate"}))
        with mock.patch.object(main, "STATS_PATH", cache):
            with mock.patch.object(main, "_get_client") as mock_client:
                stats = main.fetch_stats(force_refresh=False)
                assert stats["tweet_count"] == 50
                mock_client.assert_not_called()

    def test_force_refresh_ignores_cache(self, tmp_path):
        cache = tmp_path / "x-stats.json"
        cache.write_text(json.dumps({"tweet_count": 50}))
        with mock.patch.object(main, "STATS_PATH", cache):
            with mock.patch.object(main, "_get_client") as mock_client:
                response = mock.MagicMock()
                response.data = _user_data()
                mock_client.return_value.get_me.return_value = response

                stats = main.fetch_stats(force_refresh=True)
                assert stats["tweet_count"] == 103
                mock_client.return_value.get_me.assert_called_once()

    def test_raises_when_no_user_data(self, tmp_path):
        with mock.patch.object(main, "STATS_PATH", tmp_path / "x-stats.json"):
            with mock.patch.object(main, "_get_client") as mock_client:
                response = mock.MagicMock()
                response.data = None
                mock_client.return_value.get_me.return_value = response
                with pytest.raises(RuntimeError, match="Failed to load user data"):
                    main.fetch_stats(force_refresh=True)


class TestGetClient:
    def test_oauth1_when_all_creds_present(self):
        with mock.patch.object(main, "tweepy") as mock_tweepy:
            with mock.patch.dict(
                os.environ,
                {
                    "X_API_KEY": "k",
                    "X_API_SECRET": "s",
                    "X_ACCESS_TOKEN": "t",
                    "X_ACCESS_SECRET": "a",
                },
            ):
                with mock.patch.object(main, "X_API_KEY", "k"):
                    with mock.patch.object(main, "X_API_SECRET", "s"):
                        with mock.patch.object(main, "X_ACCESS_TOKEN", "t"):
                            with mock.patch.object(main, "X_ACCESS_SECRET", "a"):
                                main._get_client()
        mock_tweepy.Client.assert_called_once()


class TestGetClientRefreshErrors:
    """_get_client() must turn a stale/consumed refresh token (invalid_grant)
    into an actionable message instead of leaking cryptic oauthlib text, while
    still letting real config problems and transient errors through untouched."""

    def _oauth2_env(self):
        # No OAuth 1.0a creds, so _get_client() takes the OAuth 2.0 path.
        return (
            mock.patch.object(main, "X_API_KEY", ""),
            mock.patch.object(main, "X_API_SECRET", ""),
            mock.patch.object(main, "X_ACCESS_TOKEN", ""),
            mock.patch.object(main, "X_ACCESS_SECRET", ""),
            mock.patch.object(main, "X_CLIENT_ID", "cid"),
            mock.patch.object(main, "X_CLIENT_SECRET", "csec"),
        )

    def _expired_tokens(self):
        return {"access_token": "old", "refresh_token": "rtok", "obtained_at": 0, "expires_in": 1}

    def test_invalid_grant_raises_actionable_runtime_error(self):
        class InvalidGrantError(Exception):
            error = "invalid_grant"

        with contextlib.ExitStack() as stack:
            for cm in self._oauth2_env():
                stack.enter_context(cm)
            stack.enter_context(mock.patch.object(main, "_get_tokens", return_value=self._expired_tokens()))
            stack.enter_context(
                mock.patch.object(main, "_refresh_access_token", side_effect=InvalidGrantError("bad"))
            )
            with pytest.raises(RuntimeError, match="re-authorize"):
                main._get_client()

    def test_other_refresh_error_propagates_unchanged(self):
        with contextlib.ExitStack() as stack:
            for cm in self._oauth2_env():
                stack.enter_context(cm)
            stack.enter_context(mock.patch.object(main, "_get_tokens", return_value=self._expired_tokens()))
            stack.enter_context(
                mock.patch.object(main, "_refresh_access_token", side_effect=ConnectionError("net down"))
            )
            with pytest.raises(ConnectionError):
                main._get_client()

    def test_missing_token_file_runtime_error_propagates_unchanged(self):
        with contextlib.ExitStack() as stack:
            for cm in self._oauth2_env():
                stack.enter_context(cm)
            stack.enter_context(
                mock.patch.object(main, "_get_tokens", side_effect=RuntimeError("Token file not found"))
            )
            with pytest.raises(RuntimeError, match="Token file not found"):
                main._get_client()


class TestGetTokens:
    """_get_tokens() must prefer the persisted file over X_REFRESH_TOKEN — X
    rotates the refresh token on every use, so the static env var is only
    good for bootstrapping a fresh/empty data volume."""

    def test_uses_refresh_token_from_env_when_no_file_exists(self, tmp_path):
        token_path = tmp_path / "does-not-exist.json"
        with mock.patch.object(main, "X_TOKEN_FILE", str(token_path)):
            with mock.patch.object(main, "X_REFRESH_TOKEN", "rtok"):
                with mock.patch.object(
                    main, "_refresh_access_token",
                    return_value={"access_token": "newtok", "expires_in": 7200, "refresh_token": "rtok2"},
                ) as mock_refresh:
                    tokens = main._get_tokens()

        assert tokens["access_token"] == "newtok"
        mock_refresh.assert_called_once_with("rtok")
        assert json.loads(token_path.read_text())["access_token"] == "newtok"

    def test_prefers_existing_file_over_stale_env_refresh_token(self, tmp_path):
        token_path = tmp_path / "tokens.json"
        token_path.write_text(json.dumps({"access_token": "from-file", "refresh_token": "file-rtok"}))
        with mock.patch.object(main, "X_TOKEN_FILE", str(token_path)):
            with mock.patch.object(main, "X_REFRESH_TOKEN", "stale-env-rtok"):
                with mock.patch.object(main, "_refresh_access_token") as mock_refresh:
                    tokens = main._get_tokens()

        assert tokens["access_token"] == "from-file"
        mock_refresh.assert_not_called()

    def test_raises_when_no_file_and_no_env_var(self, tmp_path):
        token_path = tmp_path / "does-not-exist.json"
        with mock.patch.object(main, "X_TOKEN_FILE", str(token_path)):
            with mock.patch.object(main, "X_REFRESH_TOKEN", ""):
                with pytest.raises(RuntimeError, match="Token file not found"):
                    main._get_tokens()


class TestPublishStats:
    def test_raises_without_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="GITHUB_GIST_TOKEN"):
                gist.publish_stats({"username": "PolitiUpdate"})

    def test_creates_gist_when_no_id(self):
        resp = mock.MagicMock()
        resp.status_code = 201
        resp.json.return_value = {
            "files": {
                "x-stats.json": {"filename": "x-stats.json", "raw_url": "https://raw"}
            }
        }
        with mock.patch.dict(os.environ, {"GITHUB_GIST_TOKEN": "tok"}):
            with mock.patch("src.x_stats.gist.GIST_ID", ""):
                with mock.patch("src.x_stats.gist._find_gist_id", return_value=None):
                    with mock.patch("src.x_stats.gist.requests.post", return_value=resp):
                        url = gist.publish_stats({"tweet_count": 103})
        assert url == "https://raw"

    def test_updates_existing_gist(self):
        resp = mock.MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "files": {
                "x-stats.json": {"filename": "x-stats.json", "raw_url": "https://raw"}
            }
        }
        with mock.patch.dict(os.environ, {"GITHUB_GIST_TOKEN": "tok"}):
            with mock.patch("src.x_stats.gist.GIST_ID", "abc123"):
                with mock.patch(
                    "src.x_stats.gist._existing_filenames", return_value=["old.txt"]
                ):
                    with mock.patch("src.x_stats.gist.requests.patch", return_value=resp):
                        url = gist.publish_stats({"tweet_count": 103})
        assert url == "https://raw"


class TestMain:
    def test_skip_gist_does_not_publish(self):
        with mock.patch.object(main, "fetch_stats", return_value={"tweet_count": 1}):
            with mock.patch.object(main, "gist_publisher") as mock_gist:
                main.main(["--refresh", "--skip-gist"])
                mock_gist.publish_stats.assert_not_called()

    def test_publishes_to_gist_by_default(self):
        with mock.patch.object(main, "fetch_stats", return_value={"tweet_count": 1}):
            with mock.patch.object(
                main, "gist_publisher"
            ) as mock_gist:
                mock_gist.publish_stats.return_value = "https://raw"
                main.main(["--refresh"])
                mock_gist.publish_stats.assert_called_once_with({"tweet_count": 1})

    def test_exits_nonzero_on_error(self):
        with mock.patch.object(
            main, "fetch_stats", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(SystemExit) as exc:
                main.main([])
            assert exc.value.code == 1

    def test_gist_publish_failure_does_not_crash_job(self):
        """Stats were already fetched/cached — a transient Gist outage (e.g.
        a 503) shouldn't fail the whole job or trip the Prowl alert."""
        with mock.patch.object(main, "fetch_stats", return_value={"tweet_count": 1}):
            with mock.patch.object(main, "gist_publisher") as mock_gist:
                mock_gist.publish_stats.side_effect = RuntimeError("503 Server Error")
                main.main(["--refresh"])  # should not raise
