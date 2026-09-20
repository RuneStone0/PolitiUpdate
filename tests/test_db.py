"""Tests for db.py — SQLite deduplication and post tracking."""

import os
import sys
from datetime import datetime, timedelta, timezone

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
        assert "posted_texts" in table_names

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


class TestPostedTexts:
    def test_find_returns_none_when_unposted(self, db_path):
        assert db.find_posted_guid("Never posted this") is None

    def test_record_then_find_returns_guid(self, db_path):
        db.record_posted_texts("g1", [("Hello world", "1001")])
        assert db.find_posted_guid("Hello world") == "g1"

    def test_records_multiple_texts_in_a_thread(self, db_path):
        db.record_posted_texts("g1", [("First", "1001"), ("Second", "1002")])
        assert db.find_posted_guid("First") == "g1"
        assert db.find_posted_guid("Second") == "g1"

    def test_skips_pairs_with_no_post_id(self, db_path):
        # A later item in a thread that failed to post has no id — its
        # text must not be recorded as posted.
        db.record_posted_texts("g1", [("Posted", "1001"), ("Not posted", None)])
        assert db.find_posted_guid("Posted") == "g1"
        assert db.find_posted_guid("Not posted") is None

    def test_skips_dry_run_id(self, db_path):
        db.record_posted_texts("g1", [("Dry run text", "dry-run")])
        assert db.find_posted_guid("Dry run text") is None

    def test_recording_same_text_twice_is_a_noop(self, db_path):
        db.record_posted_texts("g1", [("Same text", "1001")])
        db.record_posted_texts("g2", [("Same text", "1002")])
        # First writer wins — the original guid stays the source of truth.
        assert db.find_posted_guid("Same text") == "g1"


# Real bodies from prod history, used to pin the dedupe threshold to measured
# behaviour rather than a guess.
KIRSTEN_UPDATE = (
    "Manden er nu fængslet for fire uger ved et lukket grundlovsforhør. Han "
    "nægter sig skyldig og afviste at udtale sig. Der blev taget forbehod for "
    "eventuel kære af fængslingen. Dommeren fængslede ham pga. risikoen for at "
    "han på fri fod ville begå ny kriminalitet."
)
SARA_NAMED = (
    "Vi er bekymret for Sara, som i nedtrykt tilstand har forladt bopælen i "
    "Hammerum ved Herning i dag ca. kl. 1250. Hun beskrives som dansk kvinde, "
    "33 år, 175-180 cm. høj, spinkel af bygning, mørkt/rødt hår, iført rød t- "
    "shirt, blå cowboybukser, mørke sko, medbragt tøj i bæreposer. Har du set "
    "Sara vil Midt- og Vestjyllands Politi gerne kontaktes på 114."
)
SARA_SCRUBBED = (
    "Vi er bekymret for X, som i nedtrykt tilstand har forladt bopælen i "
    "Hammerum ved Herning i dag ca. kl. 1250. X beskrives som dansk kvinde, "
    "33 år, X cm høj, spinkel af bygning, X hår, iført rød t- shirt, blå "
    "cowboybukser, mørke sko, medbragt tøj i bæreposer. Har du set X vil Midt- "
    "og Vestjyllands Politi gerne kontaktes på 114."
)


def _age_post(guid, hours, status="posted"):
    """Backdate a row's posted_at (save_post always stamps 'now')."""
    conn = db.get_conn()
    conn.execute(
        "UPDATE posts SET posted_at = ?, status = ? WHERE guid = ?",
        (
            (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(),
            status,
            guid,
        ),
    )
    conn.commit()
    conn.close()


class TestFindRecentSimilarPost:
    def test_none_for_empty_body(self, db_path):
        assert db.find_recent_similar_post("", "g2") is None
        assert db.find_recent_similar_post("   ", "g2") is None

    def test_none_when_nothing_posted(self, db_path):
        assert db.find_recent_similar_post("Anything", "g2") is None

    def test_identical_body_under_a_different_release_is_a_duplicate(self, db_path):
        # The Kirsten case: the feed published the same update twice, under two
        # pressemeddelelse ids, rendered with different district prefixes.
        db.save_post("https://x/15170166/a#sm-1", "Titel", KIRSTEN_UPDATE,
                     status="posted", x_post_id="111")
        dup = db.find_recent_similar_post(
            KIRSTEN_UPDATE, "https://x/15170297/b#sm-2"
        )
        assert dup is not None
        assert dup["x_post_id"] == "111"
        assert dup["similarity"] == 1.0

    def test_same_release_is_never_a_duplicate(self, db_path):
        # Another update on the same press release is a legitimate thread item.
        db.save_post("https://x/15170166/a#sm-1", "Titel", KIRSTEN_UPDATE,
                     status="posted", x_post_id="111")
        assert db.find_recent_similar_post(
            KIRSTEN_UPDATE, "https://x/15170166/a#sm-2"
        ) is None

    def test_only_posted_rows_count(self, db_path):
        db.save_post("https://x/15170166/a#sm-1", "Titel", KIRSTEN_UPDATE,
                     status="failed")
        assert db.find_recent_similar_post(KIRSTEN_UPDATE, "https://x/other") is None

    def test_outside_the_window_is_not_a_duplicate(self, db_path):
        db.save_post("https://x/15170166/a#sm-1", "Titel", KIRSTEN_UPDATE,
                     status="posted", x_post_id="111")
        _age_post("https://x/15170166/a#sm-1", hours=30)
        assert db.find_recent_similar_post(
            KIRSTEN_UPDATE, "https://x/other", within_hours=24
        ) is None
        assert db.find_recent_similar_post(
            KIRSTEN_UPDATE, "https://x/other", within_hours=48
        ) is not None

    def test_scrubbed_name_republication_still_posts(self, db_path):
        """Measured at 0.95 similarity: the police re-publish a missing-person
        appeal with the name removed after the person is found. That is a
        correction, not a duplicate — the default threshold must let it through."""
        db.save_post("https://x/sara-named", "Har du set Sara?", SARA_NAMED,
                     status="posted", x_post_id="222")
        assert db.find_recent_similar_post(
            SARA_SCRUBBED, "https://x/sara-anon"
        ) is None

    def test_threshold_is_configurable(self, db_path):
        db.save_post("https://x/sara-named", "Har du set Sara?", SARA_NAMED,
                     status="posted", x_post_id="222")
        dup = db.find_recent_similar_post(
            SARA_SCRUBBED, "https://x/sara-anon", threshold=0.90
        )
        assert dup is not None and dup["x_post_id"] == "222"

    def test_whitespace_differences_do_not_hide_a_duplicate(self, db_path):
        db.save_post("https://x/a#sm-1", "Titel", KIRSTEN_UPDATE,
                     status="posted", x_post_id="111")
        assert db.find_recent_similar_post(
            KIRSTEN_UPDATE.replace(" ", "\n"), "https://x/b#sm-2"
        ) is not None


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
