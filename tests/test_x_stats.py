"""Tests for src.x_stats — X stats fetch, cache, and gist publish."""

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
