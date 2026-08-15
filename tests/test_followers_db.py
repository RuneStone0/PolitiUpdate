"""Tests for src.followers.db — SQLite follower tracking."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import src.followers.config as config  # noqa: E402
import src.followers.db as db  # noqa: E402


@pytest.fixture
def db_path(temp_db):
    old = config.DB_PATH
    config.DB_PATH = temp_db
    db.init_db()
    yield temp_db
    config.DB_PATH = old


class TestInitDb:
    def test_creates_table(self, db_path):
        conn = db.get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        assert "followers" in [t[0] for t in tables]

    def test_idempotent_init(self, db_path):
        db.init_db()
        db.init_db()
        assert True


class TestGetKnownIds:
    def test_empty_initially(self, db_path):
        assert db.get_known_ids() == set()

    def test_returns_upserted_ids(self, db_path):
        db.upsert_follower("1", "alice", followed_back=True)
        db.upsert_follower("2", "bob", followed_back=False)
        assert db.get_known_ids() == {"1", "2"}


class TestGetFollower:
    def test_returns_none_when_missing(self, db_path):
        assert db.get_follower("nope") is None

    def test_returns_row(self, db_path):
        db.upsert_follower("1", "alice", followed_back=True)
        row = db.get_follower("1")
        assert row == {"user_id": "1", "username": "alice", "followed_back": True}


class TestUpsertFollower:
    def test_inserts_new(self, db_path):
        db.upsert_follower("1", "alice", followed_back=False)
        row = db.get_follower("1")
        assert row["followed_back"] is False

    def test_followed_back_is_sticky(self, db_path):
        """Once followed_back is set, a later upsert with False must not clear it."""
        db.upsert_follower("1", "alice", followed_back=True)
        db.upsert_follower("1", "alice", followed_back=False)
        assert db.get_follower("1")["followed_back"] is True

    def test_updates_username(self, db_path):
        db.upsert_follower("1", "old_name", followed_back=False)
        db.upsert_follower("1", "new_name", followed_back=False)
        assert db.get_follower("1")["username"] == "new_name"


class TestMarkFollowedBack:
    def test_sets_flag(self, db_path):
        db.upsert_follower("1", "alice", followed_back=False)
        db.mark_followed_back("1")
        assert db.get_follower("1")["followed_back"] is True


class TestRemoveFollower:
    def test_removes_row(self, db_path):
        db.upsert_follower("1", "alice", followed_back=True)
        db.remove_follower("1")
        assert db.get_follower("1") is None

    def test_noop_when_missing(self, db_path):
        db.remove_follower("does-not-exist")
        assert True


class TestGetConn:
    def test_creates_db_directory(self, temp_db):
        old = config.DB_PATH
        config.DB_PATH = temp_db
        try:
            conn = db.get_conn()
            conn.close()
            assert os.path.exists(temp_db)
        finally:
            config.DB_PATH = old
