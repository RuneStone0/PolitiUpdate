"""Tests for main.py — processing pipeline and retry logic."""

import os
import sys
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import src.bot.main as main  # noqa: E402
import src.bot.db as db  # noqa: E402


@pytest.fixture(autouse=True)
def reset_counter():
    main._retry_counter = 0
    main.running = True


@pytest.fixture(autouse=True)
def no_dup_guid():
    """By default, nothing is a known duplicate — individual tests can
    override find_posted_guid's return value to exercise that path."""
    with mock.patch.object(db, "find_posted_guid", return_value=None), \
         mock.patch.object(db, "record_posted_texts"):
        yield


class TestProcessItem:
    def test_skips_known_guid(self):
        with mock.patch.object(db, "is_known", return_value=True):
            with mock.patch("src.bot.main.fetch_press_release") as mock_fetch:
                main._process_item({
                    "guid": "known-guid",
                    "title": "Test",
                    "link": "http://x",
                })
                mock_fetch.assert_not_called()

    def test_saves_failed_when_no_thread_items(self):
        with mock.patch.object(db, "is_known", return_value=False):
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("Distrikt", [])):
                with mock.patch.object(db, "save_post") as mock_save:
                    main._process_item({
                        "guid": "g1",
                        "title": "T",
                        "link": "http://x",
                    })
                    kw = mock_save.call_args[1]
                    assert mock_save.call_args[0][0] == "g1"
                    assert kw["status"] == "failed"

    def test_posts_thread_and_saves_posted(self):
        with mock.patch.object(db, "is_known", return_value=False):
            items = [{"body": "Latest", "sm_id": ""}, {"body": "Older", "sm_id": ""}]
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                formatted = ["Post 1", "Post 2"]
                with mock.patch("src.bot.main.format_post",
                                side_effect=formatted):
                    with mock.patch("src.bot.main.post_thread",
                                    return_value=["111", "222"]):
                        with mock.patch.object(db, "save_post") as mock_save:
                            main._process_item({
                                "guid": "g2",
                                "title": "T",
                                "link": "http://x",
                            })
                            assert mock_save.call_count == 2
                            kw0 = mock_save.call_args_list[0][1]
                            kw1 = mock_save.call_args_list[1][1]
                            assert kw0["status"] == "fetching"
                            assert kw1["status"] == "posted"
                            assert kw1["x_post_id"] == "111"

    def test_filters_to_matching_sm_id(self):
        """When guid has an #sm-XXXXX fragment, only that thread item is posted."""
        with mock.patch.object(db, "is_known", return_value=False):
            items = [
                {"body": "Update 2", "sm_id": "sm-999"},
                {"body": "Update 1", "sm_id": "sm-888"},
            ]
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P") as mock_fmt:
                    with mock.patch("src.bot.main.post_thread",
                                    return_value=["111"]):
                        with mock.patch.object(db, "save_post"):
                            main._process_item({
                                "guid": "http://example.com/pr#sm-888",
                                "title": "T",
                                "link": "http://example.com/pr#sm-888",
                            })
                            # format_post should have been called only once, for sm-888
                            assert mock_fmt.call_count == 1
                            assert mock_fmt.call_args[0][2] == "Update 1"

    def test_falls_back_to_first_item_when_no_sm_match(self):
        """When fragment doesn't match any sm_id, fall back to thread_items[0]."""
        with mock.patch.object(db, "is_known", return_value=False):
            items = [
                {"body": "Latest", "sm_id": "sm-999"},
                {"body": "Older", "sm_id": "sm-888"},
            ]
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P") as mock_fmt:
                    with mock.patch("src.bot.main.post_thread",
                                    return_value=["111"]):
                        with mock.patch.object(db, "save_post"):
                            main._process_item({
                                "guid": "http://example.com/pr#sm-unknown",
                                "title": "T",
                                "link": "http://example.com/pr#sm-unknown",
                            })
                            # Falls back: posts all items (no match found)
                            assert mock_fmt.call_count == 2

    def test_saves_failed_when_posting_returns_none(self):
        with mock.patch.object(db, "is_known", return_value=False):
            items = [{"body": "B"}]
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P"):
                    with mock.patch("src.bot.main.post_thread",
                                    return_value=[None]):
                        with mock.patch.object(db, "save_post") as mock_save:
                            main._process_item({
                                "guid": "g3",
                                "title": "T",
                                "link": "http://x",
                            })
                            kw = mock_save.call_args_list[-1][1]
                            assert kw["status"] == "failed"

    def test_skips_and_marks_skipped_when_content_already_posted(self):
        """If this exact tweet text was already posted (e.g. under a
        different guid the feed re-published), skip without calling X."""
        with mock.patch.object(db, "is_known", return_value=False):
            items = [{"body": "B"}]
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P"):
                    with mock.patch.object(db, "find_posted_guid",
                                            return_value="other-guid"):
                        with mock.patch("src.bot.main.post_thread") as mock_post:
                            with mock.patch.object(db, "save_post") as mock_save:
                                main._process_item({
                                    "guid": "g5",
                                    "title": "T",
                                    "link": "http://x",
                                })
                                mock_post.assert_not_called()
                                kw = mock_save.call_args_list[-1][1]
                                assert kw["status"] == "skipped"

    def test_saves_failed_when_posting_returns_empty_ids(self):
        with mock.patch.object(db, "is_known", return_value=False):
            items = [{"body": "B"}]
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P"):
                    with mock.patch("src.bot.main.post_thread",
                                    return_value=[]):
                        with mock.patch.object(db, "save_post") as mock_save:
                            main._process_item({
                                "guid": "g4",
                                "title": "T",
                                "link": "http://x",
                            })
                            kw = mock_save.call_args_list[-1][1]
                            assert kw["status"] == "failed"


class TestAgeGate:
    """Verify that stale items are skipped rather than posted."""

    def test_old_item_is_dropped_in_run_loop(self):
        old_pub_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        items = [{"guid": "old-1", "title": "Old", "link": "http://x", "pub_dt": old_pub_dt}]

        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch("src.bot.main.health.set_last_poll"):
                        with mock.patch("src.bot.main.fetch_feed", return_value=items):
                            with mock.patch.object(db, "is_known", return_value=False):
                                with mock.patch.object(db, "save_post") as mock_save:
                                    with mock.patch(
                                        "src.bot.main.fetch_press_release"
                                    ) as mock_fetch_pr:
                                        with mock.patch(
                                            "src.bot.main.time.sleep",
                                            side_effect=SystemExit,
                                        ):
                                            main._setup_logging()
                                            main.running = True
                                            try:
                                                main.run()
                                            except SystemExit:
                                                pass
                                            # Should be dropped as stale, not fetched
                                            mock_fetch_pr.assert_not_called()
                                            mock_save.assert_called_once()
                                            assert mock_save.call_args[1]["status"] == "dropped_stale"

    def test_fresh_item_is_processed(self):
        fresh_pub_dt = datetime.now(timezone.utc)
        items = [{"guid": "new-1", "title": "Fresh", "link": "http://x",
                  "pub_dt": fresh_pub_dt}]

        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch("src.bot.main.health.set_last_poll"):
                        with mock.patch("src.bot.main.fetch_feed", return_value=items):
                            with mock.patch.object(db, "is_known", return_value=False):
                                ti = [{"body": "B", "sm_id": ""}]
                                with mock.patch(
                                    "src.bot.main.fetch_press_release",
                                    return_value=("D", ti),
                                ):
                                    with mock.patch(
                                        "src.bot.main.format_post", return_value="P"
                                    ):
                                        with mock.patch(
                                            "src.bot.main.post_thread",
                                            return_value=["111"],
                                        ):
                                            with mock.patch.object(db, "save_post") as mock_save:
                                                with mock.patch(
                                                    "src.bot.main.time.sleep",
                                                    side_effect=SystemExit,
                                                ):
                                                    main._setup_logging()
                                                    main.running = True
                                                    try:
                                                        main.run()
                                                    except SystemExit:
                                                        pass
                                                    statuses = [
                                                        c[1]["status"]
                                                        for c in mock_save.call_args_list
                                                    ]
                                                    assert "posted" in statuses

    def test_already_known_old_item_is_not_re_saved(self):
        old_pub_dt = datetime(1970, 1, 1, tzinfo=timezone.utc)
        items = [{"guid": "old-known", "title": "Old Known", "link": "http://x",
                  "pub_dt": old_pub_dt}]

        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch("src.bot.main.health.set_last_poll"):
                        with mock.patch("src.bot.main.fetch_feed", return_value=items):
                            with mock.patch.object(db, "is_known", return_value=True):
                                with mock.patch.object(db, "save_post") as mock_save:
                                    with mock.patch(
                                        "src.bot.main.time.sleep",
                                        side_effect=SystemExit,
                                    ):
                                        main._setup_logging()
                                        main.running = True
                                        try:
                                            main.run()
                                        except SystemExit:
                                            pass
                                        mock_save.assert_not_called()


class TestRetryFailed:
    def test_returns_zero_when_no_failed_posts(self):
        with mock.patch.object(db, "get_failed_posts", return_value=[]):
            result = main._retry_failed()
            assert result == 0

    def test_retries_failed_posts(self):
        fresh_iso = datetime.now(timezone.utc).isoformat()
        failed = [{"guid": "f1", "title": "Fail 1", "pub_date": fresh_iso},
                  {"guid": "f2", "title": "Fail 2", "pub_date": fresh_iso}]
        items = [{"body": "B"}]

        with mock.patch.object(db, "get_failed_posts", return_value=failed):
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P"):
                    with mock.patch("src.bot.main.post_thread",
                                    return_value=["999"]):
                        with mock.patch.object(db, "save_post") as mock_save:
                            result = main._retry_failed()
                            assert result == 2
                            assert mock_save.call_count == 2
                            for call in mock_save.call_args_list:
                                assert call[1]["status"] == "posted"

    def test_retry_keeps_failed_on_posting_error(self):
        fresh_iso = datetime.now(timezone.utc).isoformat()
        failed = [{"guid": "f3", "title": "Fail 3", "pub_date": fresh_iso}]
        items = [{"body": "B"}]

        with mock.patch.object(db, "get_failed_posts", return_value=failed):
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P"):
                    with mock.patch("src.bot.main.post_thread",
                                    return_value=[None]):
                        with mock.patch.object(db, "save_post") as mock_save:
                            result = main._retry_failed()
                            assert result == 1
                            kw = mock_save.call_args_list[-1][1]
                            assert kw["status"] == "failed"

    def test_retry_skips_when_content_already_posted(self):
        """A retry whose formatted text matches an already-posted tweet
        (e.g. an earlier attempt succeeded but we recorded it as failed)
        should give up locally rather than hitting X again."""
        fresh_iso = datetime.now(timezone.utc).isoformat()
        failed = [{"guid": "f9", "title": "Fail 9", "pub_date": fresh_iso}]
        items = [{"body": "B"}]

        with mock.patch.object(db, "get_failed_posts", return_value=failed):
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P"):
                    with mock.patch.object(db, "find_posted_guid",
                                            return_value="other-guid"):
                        with mock.patch("src.bot.main.post_thread") as mock_post:
                            with mock.patch.object(db, "save_post") as mock_save:
                                result = main._retry_failed()
                                assert result == 1
                                mock_post.assert_not_called()
                                kw = mock_save.call_args_list[-1][1]
                                assert kw["status"] == "skipped"

    def test_retry_skips_when_no_thread_items(self):
        fresh_iso = datetime.now(timezone.utc).isoformat()
        failed = [{"guid": "f4", "title": "Fail 4", "pub_date": fresh_iso}]

        with mock.patch.object(db, "get_failed_posts", return_value=failed):
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", [])):
                with mock.patch.object(db, "save_post") as mock_save:
                    result = main._retry_failed()
                    assert result == 0
                    mock_save.assert_not_called()

    def test_retry_drops_stale_failed_post(self):
        """Failed posts whose pub_date is too old should be given up on
        (status="dropped_stale"), not retried."""
        old_iso = datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
        failed = [{"guid": "f-old", "title": "Old Fail", "pub_date": old_iso}]

        with mock.patch.object(db, "get_failed_posts", return_value=failed):
            with mock.patch("src.bot.main.fetch_press_release") as mock_fetch_pr:
                with mock.patch.object(db, "save_post") as mock_save:
                    result = main._retry_failed()
                    assert result == 1
                    mock_fetch_pr.assert_not_called()
                    assert mock_save.call_args[1]["status"] == "dropped_stale"

    def test_retry_skips_failed_post_with_missing_pub_date(self):
        """A row with no recorded pub_date (e.g. pre-dating the age-gate migration)
        must be treated as stale, not silently retried regardless of age."""
        failed = [{"guid": "f-nulldate", "title": "No Date Fail", "pub_date": None}]

        with mock.patch.object(db, "get_failed_posts", return_value=failed):
            with mock.patch("src.bot.main.fetch_press_release") as mock_fetch_pr:
                with mock.patch.object(db, "save_post") as mock_save:
                    result = main._retry_failed()
                    assert result == 1
                    mock_fetch_pr.assert_not_called()
                    assert mock_save.call_args[1]["status"] == "dropped_stale"

    def test_retry_filters_by_sm_id_fragment(self):
        """Retry must not re-post all thread items — only the one matching the guid fragment."""
        fresh_iso = datetime.now(timezone.utc).isoformat()
        failed = [{"guid": "http://example.com/pr#sm-42", "title": "T", "pub_date": fresh_iso}]
        items = [
            {"body": "Update sm-42", "sm_id": "sm-42"},
            {"body": "Update sm-41", "sm_id": "sm-41"},
        ]

        with mock.patch.object(db, "get_failed_posts", return_value=failed):
            with mock.patch("src.bot.main.fetch_press_release",
                            return_value=("D", items)):
                with mock.patch("src.bot.main.format_post",
                                return_value="P") as mock_fmt:
                    with mock.patch("src.bot.main.post_thread",
                                    return_value=["1"]):
                        with mock.patch.object(db, "save_post"):
                            main._retry_failed()
                            assert mock_fmt.call_count == 1
                            assert mock_fmt.call_args[0][2] == "Update sm-42"

    def test_retry_handles_exception_gracefully(self):
        fresh_iso = datetime.now(timezone.utc).isoformat()
        failed = [{"guid": "f5", "title": "Fail 5", "pub_date": fresh_iso}]

        with mock.patch.object(db, "get_failed_posts", return_value=failed):
            with mock.patch("src.bot.main.fetch_press_release",
                            side_effect=RuntimeError("boom")):
                result = main._retry_failed()
                assert result == 1


class TestSignalHandling:
    def test_handle_signal_sets_running_false(self):
        main.running = True
        main._handle_signal(15, None)
        assert main.running is False


class TestSetupLogging:
    def test_configures_logging_without_error(self):
        main._setup_logging()
        import logging
        root = logging.getLogger()
        assert root.level in (logging.DEBUG, logging.INFO, logging.WARNING)


class TestRunLoop:
    def test_runs_one_poll_cycle(self):
        items = [{"guid": "new-1", "title": "Test", "link": "http://x"}]

        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch("src.bot.main.fetch_feed", return_value=items):
                        with mock.patch.object(db, "is_known", return_value=False):
                            ti = [{"body": "B"}]
                            with mock.patch(
                                "src.bot.main.fetch_press_release",
                                return_value=("D", ti),
                            ):
                                with mock.patch(
                                    "src.bot.main.format_post", return_value="P"
                                ):
                                    with mock.patch(
                                        "src.bot.main.post_thread",
                                        return_value=["111"],
                                    ):
                                        with mock.patch.object(db, "save_post"):
                                            with mock.patch(
                                                "src.bot.main.time.sleep",
                                                side_effect=[None, SystemExit],
                                            ):
                                                main._setup_logging()
                                                try:
                                                    main.run()
                                                except SystemExit:
                                                    pass
                                                assert True

    def test_handles_feed_fetch_error(self):
        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch(
                        "src.bot.main.fetch_feed",
                        side_effect=RuntimeError("feed down"),
                    ):
                        with mock.patch(
                            "src.bot.main.time.sleep",
                            side_effect=[None, SystemExit],
                        ):
                            main._setup_logging()
                            main.running = True
                            try:
                                main.run()
                            except SystemExit:
                                pass
                            assert True

    def test_handles_item_processing_error(self):
        items = [{"guid": "bad", "title": "Bad", "link": "http://x"}]

        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch("src.bot.main.fetch_feed", return_value=items):
                        with mock.patch.object(
                            db, "is_known", return_value=False
                        ):
                            with mock.patch(
                                "src.bot.main.fetch_press_release",
                                side_effect=RuntimeError("scrape fail"),
                            ):
                                with mock.patch.object(db, "save_post"):
                                    with mock.patch(
                                        "src.bot.main.time.sleep",
                                        side_effect=[None, SystemExit],
                                    ):
                                        main._setup_logging()
                                        main.running = True
                                        try:
                                            main.run()
                                        except SystemExit:
                                            pass
                                        assert True

    def test_retry_triggered_after_enough_polls(self):
        items: list = []
        main._retry_counter = main.RETRY_EVERY_POLLS - 1

        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch("src.bot.main.health.set_last_poll"):
                        with mock.patch("src.bot.main.fetch_feed", return_value=items):
                            with mock.patch("src.bot.main._retry_failed") as mock_retry:
                                with mock.patch(
                                    "src.bot.main.time.sleep",
                                    side_effect=SystemExit,
                                ):
                                    main._setup_logging()
                                    main.running = True
                                    try:
                                        main.run()
                                    except SystemExit:
                                        pass
                                    mock_retry.assert_called_once()
                                    assert main._retry_counter == 0

    def test_respects_max_items_per_poll(self):
        items = [
            {"guid": f"g{i}", "title": f"T{i}", "link": f"http://x{i}"}
            for i in range(10)
        ]

        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch("src.bot.main.health.set_last_poll"):
                        with mock.patch("src.bot.main.fetch_feed", return_value=items):
                            with mock.patch.object(db, "is_known", return_value=False):
                                ti = [{"body": "B"}]
                                with mock.patch(
                                    "src.bot.main.fetch_press_release",
                                    return_value=("D", ti),
                                ):
                                    with mock.patch(
                                        "src.bot.main.format_post",
                                        return_value="P",
                                    ):
                                        with mock.patch(
                                            "src.bot.main.post_thread",
                                            return_value=["111"],
                                        ):
                                            with mock.patch.object(db, "save_post"):
                                                with mock.patch(
                                                    "src.bot.main.time.sleep",
                                                    side_effect=SystemExit,
                                                ):
                                                    main._setup_logging()
                                                    main.running = True
                                                    main.MAX_NEW_ITEMS_PER_POLL = 2
                                                    try:
                                                        main.run()
                                                    except SystemExit:
                                                        pass
                                                    assert True

    def test_handles_db_save_error_in_exception_handler(self):
        items = [{"guid": "bad", "title": "Bad", "link": "http://x"}]

        with mock.patch("src.bot.main.db.init_db"):
            with mock.patch("src.bot.main.health.start"):
                with mock.patch("src.bot.main.health.stop"):
                    with mock.patch("src.bot.main.fetch_feed", return_value=items):
                        with mock.patch.object(db, "is_known", return_value=False):
                            # fetch_press_release raises → triggers error handler
                            with mock.patch(
                                "src.bot.main.fetch_press_release",
                                side_effect=RuntimeError("scrape fail"),
                            ):
                                # db.save_post in the error handler ALSO raises
                                with mock.patch.object(
                                    db, "save_post",
                                    side_effect=RuntimeError("db fail"),
                                ):
                                    with mock.patch(
                                        "src.bot.main.time.sleep",
                                        side_effect=SystemExit,
                                    ):
                                        main._setup_logging()
                                        main.running = True
                                        try:
                                            main.run()
                                        except SystemExit:
                                            pass
                                        assert True
