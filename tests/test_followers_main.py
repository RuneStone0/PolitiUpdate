"""Tests for src.followers.main — follower sync (follow-back / unfollow)."""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import tweepy  # noqa: E402

import src.followers.config as config  # noqa: E402
import src.followers.db as db  # noqa: E402
import src.followers.main as main  # noqa: E402


@pytest.fixture
def db_path(temp_db):
    old = config.DB_PATH
    config.DB_PATH = temp_db
    db.init_db()
    yield temp_db
    config.DB_PATH = old


def _user(uid, username):
    u = mock.MagicMock()
    u.id = uid
    u.username = username
    return u


def _followers_response(users, next_token=None):
    resp = mock.MagicMock()
    resp.data = users
    resp.meta = {"next_token": next_token} if next_token else {}
    return resp


class TestFetchAllFollowers:
    def test_single_page(self):
        client = mock.MagicMock()
        client.get_users_followers.return_value = _followers_response(
            [_user(1, "alice"), _user(2, "bob")]
        )
        result = main._fetch_all_followers(client, "oauth1", "999")
        assert result == {"1": "alice", "2": "bob"}
        client.get_users_followers.assert_called_once()

    def test_paginates(self):
        client = mock.MagicMock()
        client.get_users_followers.side_effect = [
            _followers_response([_user(1, "alice")], next_token="page2"),
            _followers_response([_user(2, "bob")]),
        ]
        result = main._fetch_all_followers(client, "oauth1", "999")
        assert result == {"1": "alice", "2": "bob"}
        assert client.get_users_followers.call_count == 2

    def test_retries_after_rate_limit(self, monkeypatch):
        monkeypatch.setattr(main.time, "sleep", lambda s: None)
        client = mock.MagicMock()
        client.get_users_followers.side_effect = [
            tweepy.TooManyRequests(response=mock.MagicMock()),
            _followers_response([_user(1, "alice")]),
        ]
        result = main._fetch_all_followers(client, "oauth1", "999")
        assert result == {"1": "alice"}

    def test_oauth2_passes_user_auth_false(self):
        client = mock.MagicMock()
        client.get_users_followers.return_value = _followers_response([])
        main._fetch_all_followers(client, "oauth2", "999")
        _, kwargs = client.get_users_followers.call_args
        assert kwargs["user_auth"] is False


class TestFollow:
    def test_dry_run_does_not_call_api(self):
        client = mock.MagicMock()
        assert main._follow(client, "oauth1", "1", "alice", dry_run=True) is True
        client.follow_user.assert_not_called()

    def test_success(self):
        client = mock.MagicMock()
        assert main._follow(client, "oauth1", "1", "alice", dry_run=False) is True
        client.follow_user.assert_called_once_with("1")

    def test_rate_limited_returns_false(self, monkeypatch):
        monkeypatch.setattr(main.time, "sleep", lambda s: None)
        client = mock.MagicMock()
        client.follow_user.side_effect = tweepy.TooManyRequests(response=mock.MagicMock())
        assert main._follow(client, "oauth1", "1", "alice", dry_run=False) is False

    def test_api_error_returns_false(self):
        client = mock.MagicMock()
        client.follow_user.side_effect = tweepy.TweepyException("boom")
        assert main._follow(client, "oauth1", "1", "alice", dry_run=False) is False


class TestUnfollow:
    def test_dry_run_does_not_call_api(self):
        client = mock.MagicMock()
        assert main._unfollow(client, "oauth1", "1", "alice", dry_run=True) is True
        client.unfollow_user.assert_not_called()

    def test_success(self):
        client = mock.MagicMock()
        assert main._unfollow(client, "oauth1", "1", "alice", dry_run=False) is True
        client.unfollow_user.assert_called_once_with("1")

    def test_api_error_returns_false(self):
        client = mock.MagicMock()
        client.unfollow_user.side_effect = tweepy.TweepyException("boom")
        assert main._unfollow(client, "oauth1", "1", "alice", dry_run=False) is False


class TestSync:
    def _setup_client(self, followers):
        client = mock.MagicMock()
        me = mock.MagicMock()
        me.data.id = 999
        client.get_me.return_value = me
        client.get_users_followers.return_value = _followers_response(
            [_user(uid, name) for uid, name in followers]
        )
        return client

    def test_follows_back_new_followers(self, db_path, monkeypatch):
        client = self._setup_client([("1", "alice"), ("2", "bob")])
        monkeypatch.setattr(main, "get_client", lambda: (client, "oauth1"))

        summary = main.sync(dry_run=False)

        assert summary == {"followers_count": 2, "followed_back": 2, "unfollowed": 0}
        assert client.follow_user.call_count == 2
        assert db.get_known_ids() == {"1", "2"}
        assert db.get_follower("1")["followed_back"] is True

    def test_unfollows_users_who_unfollowed(self, db_path, monkeypatch):
        db.upsert_follower("1", "alice", followed_back=True)
        db.upsert_follower("2", "bob", followed_back=True)
        # Only "1" still follows us — "2" unfollowed.
        client = self._setup_client([("1", "alice")])
        monkeypatch.setattr(main, "get_client", lambda: (client, "oauth1"))

        summary = main.sync(dry_run=False)

        assert summary == {"followers_count": 1, "followed_back": 0, "unfollowed": 1}
        client.unfollow_user.assert_called_once_with("2")
        assert db.get_known_ids() == {"1"}

    def test_retries_previously_failed_follow(self, db_path, monkeypatch):
        db.upsert_follower("1", "alice", followed_back=False)
        client = self._setup_client([("1", "alice")])
        monkeypatch.setattr(main, "get_client", lambda: (client, "oauth1"))

        summary = main.sync(dry_run=False)

        assert summary["followed_back"] == 1
        assert db.get_follower("1")["followed_back"] is True

    def test_dry_run_makes_no_api_calls_and_no_db_writes(self, db_path, monkeypatch):
        client = self._setup_client([("1", "alice")])
        monkeypatch.setattr(main, "get_client", lambda: (client, "oauth1"))

        summary = main.sync(dry_run=True)

        assert summary == {"followers_count": 1, "followed_back": 1, "unfollowed": 0}
        client.follow_user.assert_not_called()
        client.unfollow_user.assert_not_called()
        assert db.get_known_ids() == set()

    def test_respects_max_actions_per_run(self, db_path, monkeypatch):
        monkeypatch.setattr(config, "MAX_ACTIONS_PER_RUN", 1)
        client = self._setup_client([("1", "alice"), ("2", "bob")])
        monkeypatch.setattr(main, "get_client", lambda: (client, "oauth1"))

        summary = main.sync(dry_run=False)

        assert summary["followed_back"] == 1
        assert client.follow_user.call_count == 1

    def test_uses_config_dry_run_default(self, db_path, monkeypatch):
        monkeypatch.setattr(config, "DRY_RUN", True)
        client = self._setup_client([("1", "alice")])
        monkeypatch.setattr(main, "get_client", lambda: (client, "oauth1"))

        main.sync()

        client.follow_user.assert_not_called()


class TestMainCli:
    def test_prints_summary_json(self, capsys):
        with mock.patch.object(main, "sync", return_value={"followers_count": 1}):
            main.main([])
        out = capsys.readouterr().out
        assert '"followers_count": 1' in out

    def test_dry_run_flag_passed_through(self):
        with mock.patch.object(main, "sync", return_value={}) as mock_sync:
            main.main(["--dry-run"])
        mock_sync.assert_called_once_with(dry_run=True)

    def test_exits_nonzero_on_error(self):
        with mock.patch.object(main, "sync", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc:
                main.main([])
            assert exc.value.code == 1
