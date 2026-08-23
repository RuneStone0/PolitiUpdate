"""Tests for src.notify — Prowl webhook, daily health check, weekly stats/followers, loop."""

import logging
import os
import sys
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import requests  # noqa: E402

import src.notify.health as health  # noqa: E402
import src.notify.log_handler as log_handler  # noqa: E402
import src.notify.loop as loop  # noqa: E402
import src.notify.main as notify_main  # noqa: E402
import src.notify.prowl as prowl  # noqa: E402
import src.notify.state as state  # noqa: E402
import src.notify.weekly as weekly  # noqa: E402


def _record(name="src.bot.main", msg="RSS fetch failed", exc_info=None, level=logging.ERROR):
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1,
        msg=msg, args=None, exc_info=exc_info,
    )


class TestProwlSend:
    def test_sends_message_and_returns_true(self):
        resp = mock.MagicMock()
        with mock.patch.object(prowl.config, "PROWL_WEBHOOK_URL", "https://example.com/hook"):
            with mock.patch.object(prowl.requests, "post", return_value=resp) as mock_post:
                ok = prowl.send("hello")
        assert ok is True
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"message": "hello"}

    def test_swallows_request_errors(self):
        with mock.patch.object(prowl.config, "PROWL_WEBHOOK_URL", "https://example.com/hook"):
            with mock.patch.object(
                prowl.requests, "post", side_effect=requests.RequestException("boom")
            ):
                ok = prowl.send("hello")
        assert ok is False

    def test_drops_message_when_url_unset(self):
        with mock.patch.object(prowl.config, "PROWL_WEBHOOK_URL", ""):
            with mock.patch.object(prowl.requests, "post") as mock_post:
                ok = prowl.send("hello")
        assert ok is False
        mock_post.assert_not_called()


class TestBotHealthCheck:
    def test_no_problems_when_healthy(self):
        resp = mock.MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"healthy": True, "checks": {"db": "ok"}}
        with mock.patch.object(health.requests, "get", return_value=resp):
            assert health._check_bot_health() == []

    def test_problem_when_unreachable(self):
        with mock.patch.object(
            health.requests, "get", side_effect=requests.RequestException("conn refused")
        ):
            problems = health._check_bot_health()
        assert len(problems) == 1
        assert "unreachable" in problems[0]

    def test_problem_when_unhealthy(self):
        resp = mock.MagicMock()
        resp.status_code = 503
        resp.json.return_value = {
            "healthy": False,
            "checks": {"db": "no such table", "rss": "reachable (200)"},
        }
        with mock.patch.object(health.requests, "get", return_value=resp):
            problems = health._check_bot_health()
        assert len(problems) == 1
        assert "no such table" in problems[0]

    def test_problem_when_non_json_response(self):
        resp = mock.MagicMock()
        resp.status_code = 500
        resp.json.side_effect = ValueError("not json")
        with mock.patch.object(health.requests, "get", return_value=resp):
            problems = health._check_bot_health()
        assert "non-JSON" in problems[0]


class TestFailedPostsCheck:
    def test_no_problem_when_db_missing(self, tmp_path):
        with mock.patch.object(health.config, "DB_PATH", str(tmp_path / "missing.db")):
            assert health._check_failed_posts() == []

    def test_no_problem_below_threshold(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE posts (guid TEXT, status TEXT)")
        conn.execute("INSERT INTO posts VALUES ('a', 'failed')")
        conn.commit()
        conn.close()
        with mock.patch.object(health.config, "DB_PATH", str(db_path)):
            with mock.patch.object(health.config, "FAILED_POSTS_THRESHOLD", 3):
                assert health._check_failed_posts() == []

    def test_problem_at_or_above_threshold(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE posts (guid TEXT, status TEXT)")
        for i in range(3):
            conn.execute("INSERT INTO posts VALUES (?, 'failed')", (str(i),))
        conn.commit()
        conn.close()
        with mock.patch.object(health.config, "DB_PATH", str(db_path)):
            with mock.patch.object(health.config, "FAILED_POSTS_THRESHOLD", 3):
                problems = health._check_failed_posts()
        assert len(problems) == 1
        assert "3 posts stuck" in problems[0]


class TestHealthRun:
    def test_sends_notification_when_problems_found(self):
        with mock.patch.object(health, "_check_bot_health", return_value=["bot down"]):
            with mock.patch.object(health, "_check_failed_posts", return_value=[]):
                with mock.patch.object(health, "send") as mock_send:
                    health.run()
        mock_send.assert_called_once()
        assert "bot down" in mock_send.call_args[0][0]

    def test_no_notification_when_healthy(self):
        with mock.patch.object(health, "_check_bot_health", return_value=[]):
            with mock.patch.object(health, "_check_failed_posts", return_value=[]):
                with mock.patch.object(health, "send") as mock_send:
                    health.run()
        mock_send.assert_not_called()


class TestDroppedPostsCheck:
    def test_no_problem_when_db_missing(self, tmp_path):
        with mock.patch.object(health.config, "DB_PATH", str(tmp_path / "missing.db")):
            assert health._check_dropped_posts("2026-01-01T00:00:00+00:00") == []

    def test_no_problem_when_nothing_dropped(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE posts (guid TEXT, title TEXT, status TEXT, posted_at TEXT)")
        conn.execute(
            "INSERT INTO posts VALUES ('a', 'T', 'posted', '2026-08-20T12:00:00+00:00')"
        )
        conn.commit()
        conn.close()
        with mock.patch.object(health.config, "DB_PATH", str(db_path)):
            assert health._check_dropped_posts("2026-08-20T00:00:00+00:00") == []

    def test_ignores_drops_before_since(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE posts (guid TEXT, title TEXT, status TEXT, posted_at TEXT)")
        conn.execute(
            "INSERT INTO posts VALUES ('a', 'Old drop', 'dropped_stale', '2026-08-19T00:00:00+00:00')"
        )
        conn.commit()
        conn.close()
        with mock.patch.object(health.config, "DB_PATH", str(db_path)):
            assert health._check_dropped_posts("2026-08-20T00:00:00+00:00") == []

    def test_reports_single_dropped_post_with_sm_id_and_link(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "test.db"
        guid = "https://via.ritzau.dk/pressemeddelelse/123/traffic-accident?lang=da#sm-123"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE posts (guid TEXT, title TEXT, status TEXT, posted_at TEXT)")
        conn.execute(
            "INSERT INTO posts VALUES (?, 'Traffic accident', 'dropped_stale', "
            "'2026-08-20T12:00:00+00:00')",
            (guid,),
        )
        conn.commit()
        conn.close()
        with mock.patch.object(health.config, "DB_PATH", str(db_path)):
            lines = health._check_dropped_posts("2026-08-20T00:00:00+00:00")
        assert len(lines) == 1
        assert "Traffic accident" in lines[0]
        assert "sm_id=sm-123" in lines[0]
        assert guid in lines[0]

    def test_falls_back_to_full_guid_when_no_fragment(self, tmp_path):
        """A guid with no #sm-XXXXX fragment should use the whole guid as
        the sm_id rather than showing an empty identifier."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE posts (guid TEXT, title TEXT, status TEXT, posted_at TEXT)")
        conn.execute(
            "INSERT INTO posts VALUES ('plain-guid', 'T', 'dropped_stale', "
            "'2026-08-20T12:00:00+00:00')"
        )
        conn.commit()
        conn.close()
        with mock.patch.object(health.config, "DB_PATH", str(db_path)):
            lines = health._check_dropped_posts("2026-08-20T00:00:00+00:00")
        assert "sm_id=plain-guid" in lines[0]

    def test_returns_all_dropped_posts_without_truncating(self, tmp_path):
        """Truncation for display is run_digest()'s job, not this
        function's — it should just report everything it finds."""
        import sqlite3

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE posts (guid TEXT, title TEXT, status TEXT, posted_at TEXT)")
        for i in range(15):
            conn.execute(
                "INSERT INTO posts VALUES (?, ?, 'dropped_stale', '2026-08-20T12:00:00+00:00')",
                (f"guid-{i}", f"Item {i}"),
            )
        conn.commit()
        conn.close()
        with mock.patch.object(health.config, "DB_PATH", str(db_path)):
            lines = health._check_dropped_posts("2026-08-20T00:00:00+00:00")
        assert len(lines) == 15


class TestRunDigest:
    def test_first_run_establishes_baseline_without_sending(self):
        with mock.patch.object(health.state, "read", return_value={}):
            with mock.patch.object(health.state, "write") as mock_write:
                with mock.patch.object(health, "_check_dropped_posts") as mock_check:
                    with mock.patch.object(health, "send") as mock_send:
                        health.run_digest()
        mock_check.assert_not_called()
        mock_send.assert_not_called()
        mock_write.assert_called_once()
        assert "last_digest_check" in mock_write.call_args[0][0]

    def test_sends_when_problems_found(self):
        since = "2026-08-20T00:00:00+00:00"
        with mock.patch.object(health.state, "read", return_value={"last_digest_check": since}):
            with mock.patch.object(health.state, "write"):
                with mock.patch.object(
                    health, "_check_dropped_posts",
                    return_value=["Title X (sm_id=sm-1) — https://example.com/x#sm-1"],
                ) as mock_check:
                    with mock.patch.object(health, "send") as mock_send:
                        health.run_digest()
        mock_check.assert_called_once_with(since)
        mock_send.assert_called_once()
        message = mock_send.call_args[0][0]
        assert "1 post(s) dropped as stale" in message
        assert "Title X (sm_id=sm-1) — https://example.com/x#sm-1" in message

    def test_truncates_long_list_of_dropped_posts(self):
        """A large batch of drops (e.g. a sustained outage) should list only
        the first _MAX_DROPPED_POSTS_SHOWN in detail, summarizing the rest."""
        since = "2026-08-20T00:00:00+00:00"
        dropped = [f"Item {i} (sm_id=sm-{i}) — https://example.com/{i}" for i in range(15)]
        with mock.patch.object(health.state, "read", return_value={"last_digest_check": since}):
            with mock.patch.object(health.state, "write"):
                with mock.patch.object(health, "_check_dropped_posts", return_value=dropped):
                    with mock.patch.object(health, "send") as mock_send:
                        health.run_digest()
        message = mock_send.call_args[0][0]
        assert "15 post(s) dropped as stale" in message
        assert "Item 0" in message
        assert f"Item {health._MAX_DROPPED_POSTS_SHOWN - 1}" in message
        assert "Item 10" not in message  # beyond the shown cap
        assert "(+5 more)" in message

    def test_no_send_when_nothing_dropped(self):
        since = "2026-08-20T00:00:00+00:00"
        with mock.patch.object(health.state, "read", return_value={"last_digest_check": since}):
            with mock.patch.object(health.state, "write"):
                with mock.patch.object(health, "_check_dropped_posts", return_value=[]):
                    with mock.patch.object(health, "send") as mock_send:
                        health.run_digest()
        mock_send.assert_not_called()

    def test_always_advances_last_digest_check(self):
        since = "2026-08-20T00:00:00+00:00"
        with mock.patch.object(health.state, "read", return_value={"last_digest_check": since}):
            with mock.patch.object(health.state, "write") as mock_write:
                with mock.patch.object(health, "_check_dropped_posts", return_value=[]):
                    with mock.patch.object(health, "send"):
                        health.run_digest()
        mock_write.assert_called_once()
        new_value = mock_write.call_args[0][0]["last_digest_check"]
        assert new_value != since


class TestState:
    def test_read_returns_empty_dict_when_missing(self, tmp_path):
        with mock.patch.object(state.config, "STATE_PATH", str(tmp_path / "missing.json")):
            assert state.read() == {}

    def test_write_then_read_roundtrips(self, tmp_path):
        state_path = tmp_path / "sub" / "notify_state.json"
        with mock.patch.object(state.config, "STATE_PATH", str(state_path)):
            state.write({"followers_count": 100})
            assert state.read() == {"followers_count": 100}

    def test_write_merges_rather_than_overwrites(self, tmp_path):
        state_path = tmp_path / "notify_state.json"
        with mock.patch.object(state.config, "STATE_PATH", str(state_path)):
            state.write({"followers_count": 100})
            state.write({"last_daily_run": "2026-08-15"})
            assert state.read() == {"followers_count": 100, "last_daily_run": "2026-08-15"}


class TestWeeklyRun:
    def test_first_run_reports_baseline(self):
        with mock.patch.object(weekly, "fetch_stats", return_value={"followers_count": 100}):
            with mock.patch.object(weekly, "publish_stats") as mock_publish:
                with mock.patch.object(weekly.state, "read", return_value={}):
                    with mock.patch.object(weekly.state, "write") as mock_write:
                        with mock.patch.object(weekly, "send") as mock_send:
                            weekly.run()
        assert "baseline of 100" in mock_send.call_args[0][0]
        mock_publish.assert_called_once_with({"followers_count": 100})
        mock_write.assert_called_once_with({"followers_count": 100})

    def test_reports_positive_delta(self):
        with mock.patch.object(weekly, "fetch_stats", return_value={"followers_count": 100}):
            with mock.patch.object(weekly, "publish_stats"):
                with mock.patch.object(weekly.state, "read", return_value={"followers_count": 90}):
                    with mock.patch.object(weekly.state, "write"):
                        with mock.patch.object(weekly, "send") as mock_send:
                            weekly.run()
        message = mock_send.call_args[0][0]
        assert "+10 new followers" in message
        assert "100 total" in message

    def test_reports_negative_delta(self):
        with mock.patch.object(weekly, "fetch_stats", return_value={"followers_count": 100}):
            with mock.patch.object(weekly, "publish_stats"):
                with mock.patch.object(weekly.state, "read", return_value={"followers_count": 110}):
                    with mock.patch.object(weekly.state, "write"):
                        with mock.patch.object(weekly, "send") as mock_send:
                            weekly.run()
        message = mock_send.call_args[0][0]
        assert "-10 new followers" in message

    def test_gist_publish_failure_is_non_fatal(self):
        with mock.patch.object(weekly, "fetch_stats", return_value={"followers_count": 100}):
            with mock.patch.object(weekly, "publish_stats", side_effect=RuntimeError("no token")):
                with mock.patch.object(weekly.state, "read", return_value={}):
                    with mock.patch.object(weekly.state, "write"):
                        with mock.patch.object(weekly, "send") as mock_send:
                            weekly.run()  # must not raise
        mock_send.assert_called_once()


class TestLoop:
    def test_daily_runs_once_hour_reached_and_not_already_run(self):
        now = datetime(2026, 8, 15, 9, 30, tzinfo=timezone.utc)  # Saturday
        with mock.patch.object(loop.config, "DAILY_HOUR_UTC", 9):
            with mock.patch.object(loop.state, "read", return_value={}):
                with mock.patch.object(loop.state, "write") as mock_write:
                    with mock.patch.object(loop.health, "run") as mock_health:
                        loop._maybe_run_daily(now)
        mock_health.assert_called_once()
        mock_write.assert_called_once_with({"last_daily_run": "2026-08-15"})

    def test_daily_skips_before_configured_hour(self):
        now = datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)
        with mock.patch.object(loop.config, "DAILY_HOUR_UTC", 9):
            with mock.patch.object(loop.state, "read", return_value={}):
                with mock.patch.object(loop.health, "run") as mock_health:
                    loop._maybe_run_daily(now)
        mock_health.assert_not_called()

    def test_daily_skips_if_already_run_today(self):
        now = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
        with mock.patch.object(loop.config, "DAILY_HOUR_UTC", 9):
            with mock.patch.object(loop.state, "read", return_value={"last_daily_run": "2026-08-15"}):
                with mock.patch.object(loop.health, "run") as mock_health:
                    loop._maybe_run_daily(now)
        mock_health.assert_not_called()

    def test_weekly_runs_on_configured_weekday_and_hour(self):
        now = datetime(2026, 8, 16, 10, 30, tzinfo=timezone.utc)  # Sunday
        with mock.patch.object(loop.config, "WEEKLY_WEEKDAY", 6):
            with mock.patch.object(loop.config, "WEEKLY_HOUR_UTC", 10):
                with mock.patch.object(loop.state, "read", return_value={}):
                    with mock.patch.object(loop.state, "write") as mock_write:
                        with mock.patch.object(loop.weekly, "run") as mock_weekly:
                            loop._maybe_run_weekly(now)
        mock_weekly.assert_called_once()
        assert mock_write.call_args[0][0]["last_weekly_run"] == "2026-W33"

    def test_weekly_skips_on_wrong_weekday(self):
        now = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)  # Saturday
        with mock.patch.object(loop.config, "WEEKLY_WEEKDAY", 6):
            with mock.patch.object(loop.state, "read", return_value={}):
                with mock.patch.object(loop.weekly, "run") as mock_weekly:
                    loop._maybe_run_weekly(now)
        mock_weekly.assert_not_called()

    def test_weekly_skips_if_already_run_this_week(self):
        now = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)  # Sunday
        with mock.patch.object(loop.config, "WEEKLY_WEEKDAY", 6):
            with mock.patch.object(loop.config, "WEEKLY_HOUR_UTC", 10):
                with mock.patch.object(loop.state, "read", return_value={"last_weekly_run": "2026-W33"}):
                    with mock.patch.object(loop.weekly, "run") as mock_weekly:
                        loop._maybe_run_weekly(now)
        mock_weekly.assert_not_called()

    def test_digest_runs_when_never_checked_before(self):
        now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
        with mock.patch.object(loop.state, "read", return_value={}):
            with mock.patch.object(loop.health, "run_digest") as mock_digest:
                loop._maybe_run_digest(now)
        mock_digest.assert_called_once()

    def test_digest_skips_before_interval_elapsed(self):
        now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
        last = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc).isoformat()  # 2h ago
        with mock.patch.object(loop.config, "DIGEST_INTERVAL_HOURS", 4):
            with mock.patch.object(loop.state, "read", return_value={"last_digest_check": last}):
                with mock.patch.object(loop.health, "run_digest") as mock_digest:
                    loop._maybe_run_digest(now)
        mock_digest.assert_not_called()

    def test_digest_runs_once_interval_elapsed(self):
        now = datetime(2026, 8, 20, 14, 1, tzinfo=timezone.utc)
        last = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc).isoformat()  # 4h1m ago
        with mock.patch.object(loop.config, "DIGEST_INTERVAL_HOURS", 4):
            with mock.patch.object(loop.state, "read", return_value={"last_digest_check": last}):
                with mock.patch.object(loop.health, "run_digest") as mock_digest:
                    loop._maybe_run_digest(now)
        mock_digest.assert_called_once()

    def test_run_loop_stops_on_signal_and_survives_job_errors(self):
        with mock.patch.object(loop, "_maybe_run_daily", side_effect=RuntimeError("boom")):
            with mock.patch.object(loop, "_maybe_run_weekly"):
                with mock.patch.object(loop, "_maybe_run_digest"):
                    with mock.patch.object(loop.time, "sleep") as mock_sleep:

                        def _stop(*args, **kwargs):
                            loop.running = False

                        mock_sleep.side_effect = _stop
                        loop.running = True
                        loop.run()  # must not raise despite _maybe_run_daily blowing up
        mock_sleep.assert_called_once()


class TestProwlErrorHandler:
    def test_sends_message_for_error_record(self):
        handler = log_handler.ProwlErrorHandler(min_interval_seconds=60)
        with mock.patch.object(log_handler, "send") as mock_send:
            handler.emit(_record())
        mock_send.assert_called_once()
        assert "src.bot.main" in mock_send.call_args[0][0]
        assert "RSS fetch failed" in mock_send.call_args[0][0]

    def test_includes_exception_type_and_message(self):
        try:
            raise ValueError("boom")
        except ValueError:
            record = _record(exc_info=sys.exc_info())
        handler = log_handler.ProwlErrorHandler(min_interval_seconds=60)
        with mock.patch.object(log_handler, "send") as mock_send:
            handler.emit(record)
        message = mock_send.call_args[0][0]
        assert "ValueError" in message
        assert "boom" in message

    def test_deduplicates_within_cooldown(self):
        handler = log_handler.ProwlErrorHandler(min_interval_seconds=9999)
        with mock.patch.object(log_handler, "send") as mock_send:
            handler.emit(_record())
            handler.emit(_record())
        mock_send.assert_called_once()

    def test_resends_after_cooldown_expires(self):
        handler = log_handler.ProwlErrorHandler(min_interval_seconds=0)
        with mock.patch.object(log_handler, "send") as mock_send:
            handler.emit(_record())
            handler.emit(_record())
        assert mock_send.call_count == 2

    def test_skips_records_from_notify_package(self):
        handler = log_handler.ProwlErrorHandler(min_interval_seconds=60)
        with mock.patch.object(log_handler, "send") as mock_send:
            handler.emit(_record(name="src.notify.prowl", msg="Failed to send Prowl notification"))
        mock_send.assert_not_called()

    def test_emit_never_raises_on_send_failure(self):
        handler = log_handler.ProwlErrorHandler(min_interval_seconds=60)
        with mock.patch.object(log_handler, "send", side_effect=RuntimeError("boom")):
            handler.emit(_record())  # must not raise


class TestInstall:
    def test_noop_when_disabled(self):
        with mock.patch.object(log_handler.config, "ERROR_ALERTS_ENABLED", False):
            assert log_handler.install() is None

    def test_attaches_handler_to_root_logger_when_enabled(self):
        with mock.patch.object(log_handler.config, "ERROR_ALERTS_ENABLED", True):
            handler = log_handler.install()
        try:
            assert isinstance(handler, log_handler.ProwlErrorHandler)
            assert handler in logging.getLogger().handlers
        finally:
            logging.getLogger().removeHandler(handler)


class TestMain:
    def test_daily_dispatches_to_health(self):
        with mock.patch.object(notify_main.health, "run") as mock_run:
            notify_main.main(["daily"])
        mock_run.assert_called_once()

    def test_weekly_dispatches_to_weekly_module(self):
        with mock.patch.object(notify_main.weekly, "run") as mock_run:
            notify_main.main(["weekly"])
        mock_run.assert_called_once()

    def test_no_args_dispatches_to_loop(self):
        with mock.patch.object(notify_main.loop, "run") as mock_run:
            notify_main.main([])
        mock_run.assert_called_once()

    def test_exits_nonzero_on_error(self):
        with mock.patch.object(notify_main.health, "run", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc:
                notify_main.main(["daily"])
        assert exc.value.code == 1
