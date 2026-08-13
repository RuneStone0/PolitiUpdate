"""Tests for db.py — SQLite deduplication and post tracking."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import src.bot.config as config
import src.bot.db as db


@pytest.fixture
def db_path(temp_db):
    old = config.DB_PATH
    config.DB_PATH = temp_db
    db.init_db()
    yield temp_db
    config.DB_PATH = old


class TestInitDb:
    def test_creates_tables(self, db_path):
        conn = db.get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        table_names = [t[0] for t in tables]
        assert "posts" in table_names

    def test_creates_index(self, db_path):
        conn = db.get_conn()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        conn.close()
        index_names = [i[0] for i in indexes]
        assert any("posts_status" in name for name in index_names)

    def test_idempotent_init(self, db_path):
        db.init_db()
        db.init_db()
        assert True


class TestIsKnown:
    def test_returns_false_for_unknown_guid(self, db_path):
        assert not db.is_known("unknown-guid-12345")

    def test_returns_true_after_save(self, db_path):
        guid = "test-guid-001"
        db.save_post(guid, "Title", "Body", status="posted")
        assert db.is_known(guid)

    def test_returns_false_after_clear(self, db_path):
        guid = "test-guid-002"
        db.save_post(guid, "Title", "Body")
        conn = db.get_conn()
        conn.execute("DELETE FROM posts WHERE guid = ?", (guid,))
        conn.commit()
        conn.close()
        assert not db.is_known(guid)


class TestSavePost:
    def test_inserts_new_post(self, db_path):
        db.save_post("g1", "Title 1", "Body 1", status="posted", x_post_id="123")
        conn = db.get_conn()
        row = conn.execute(
            "SELECT title, body, status, x_post_id FROM posts WHERE guid = ?", ("g1",)
        ).fetchone()
        conn.close()

        assert row[0] == "Title 1"
        assert row[1] == "Body 1"
        assert row[2] == "posted"
        assert row[3] == "123"

    def test_stores_pub_date(self, db_path):
        db.save_post("g_pd", "Title", "Body", pub_date="2026-08-03T14:00:00+00:00")
        conn = db.get_conn()
        row = conn.execute(
            "SELECT pub_date FROM posts WHERE guid = ?", ("g_pd",)
        ).fetchone()
        conn.close()
        assert row[0] == "2026-08-03T14:00:00+00:00"

    def test_preserves_pub_date_on_update(self, db_path):
        db.save_post("g_pu", "Title", "Body", pub_date="2026-08-03T14:00:00+00:00")
        # Update without supplying pub_date — existing value must be kept
        db.save_post("g_pu", "Title", "Body", status="posted")
        conn = db.get_conn()
        row = conn.execute(
            "SELECT pub_date FROM posts WHERE guid = ?", ("g_pu",)
        ).fetchone()
        conn.close()
        assert row[0] == "2026-08-03T14:00:00+00:00"

    def test_updates_existing_post(self, db_path):
        db.save_post("g2", "Old Title", "Old Body", status="fetching")
        db.save_post("g2", "Old Title", "Old Body", status="posted", x_post_id="456")

        conn = db.get_conn()
        row = conn.execute(
            "SELECT status, x_post_id FROM posts WHERE guid = ?", ("g2",)
        ).fetchone()
        conn.close()

        assert row[0] == "posted"
        assert row[1] == "456"

    def test_default_status_is_pending(self, db_path):
        db.save_post("g3", "Title", "Body")
        conn = db.get_conn()
        row = conn.execute(
            "SELECT status FROM posts WHERE guid = ?", ("g3",)
        ).fetchone()
        conn.close()
        assert row[0] == "pending"

    def test_sets_posted_at_timestamp(self, db_path):
        db.save_post("g4", "Title", "Body")
        conn = db.get_conn()
        row = conn.execute(
            "SELECT posted_at FROM posts WHERE guid = ?", ("g4",)
        ).fetchone()
        conn.close()
        assert row[0] is not None
        assert "T" in row[0]

    def test_multiple_guids_are_independent(self, db_path):
        db.save_post("a", "TA", "BA", status="posted")
        db.save_post("b", "TB", "BB", status="failed")

        assert db.is_known("a")
        assert db.is_known("b")
        assert not db.is_known("c")


class TestGetFailedPosts:
    def test_returns_empty_when_no_failed(self, db_path):
        posts = db.get_failed_posts()
        assert isinstance(posts, list)
        assert len(posts) == 0

    def test_returns_failed_posts(self, db_path):
        db.save_post("f1", "Fail 1", "", status="failed",
                     pub_date="2026-08-03T14:00:00+00:00")
        db.save_post("f2", "Fail 2", "", status="failed")
        db.save_post("p1", "Posted", "", status="posted", x_post_id="123")

        posts = db.get_failed_posts()
        assert len(posts) == 2
        guids = {p["guid"] for p in posts}
        assert guids == {"f1", "f2"}
        f1 = next(p for p in posts if p["guid"] == "f1")
        assert f1["pub_date"] == "2026-08-03T14:00:00+00:00"

    def test_respects_limit(self, db_path):
        for i in range(5):
            db.save_post(f"f{i}", f"Fail {i}", "", status="failed")

        posts = db.get_failed_posts(limit=2)
        assert len(posts) == 2

    def test_returns_oldest_first(self, db_path):
        db.save_post("old", "Old", "", status="failed")
        db.save_post("new", "New", "", status="failed")

        posts = db.get_failed_posts()
        assert posts[0]["guid"] == "old"
        assert posts[1]["guid"] == "new"


class TestGetConn:
    def test_creates_db_directory(self, temp_db):
        """Ensure parent directory is created if missing."""
        old = config.DB_PATH
        config.DB_PATH = temp_db
        try:
            conn = db.get_conn()
            conn.close()
            assert os.path.exists(temp_db)
        finally:
            config.DB_PATH = old
