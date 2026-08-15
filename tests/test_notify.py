"""Tests for src.notify — Prowl webhook, daily health check, weekly followers."""

import json
import logging
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import requests  # noqa: E402

import src.notify.followers as followers  # noqa: E402
import src.notify.health as health  # noqa: E402
import src.notify.log_handler as log_handler  # noqa: E402
import src.notify.main as notify_main  # noqa: E402
import src.notify.prowl as prowl  # noqa: E402
import src.notify.state_gist as state_gist  # noqa: E402


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


class TestFollowersRun:
    def test_first_run_reports_baseline(self):
        with mock.patch.object(followers, "fetch_stats", return_value={"followers_count": 100}):
            with mock.patch.object(followers.state_gist, "read", return_value=None):
                with mock.patch.object(followers.state_gist, "write") as mock_write:
                    with mock.patch.object(followers, "send") as mock_send:
                        followers.run()
        assert "baseline of 100" in mock_send.call_args[0][0]
        mock_write.assert_called_once_with({"followers_count": 100})

    def test_reports_positive_delta(self):
        with mock.patch.object(followers, "fetch_stats", return_value={"followers_count": 100}):
            with mock.patch.object(followers.state_gist, "read", return_value={"followers_count": 90}):
                with mock.patch.object(followers.state_gist, "write"):
                    with mock.patch.object(followers, "send") as mock_send:
                        followers.run()
        message = mock_send.call_args[0][0]
        assert "+10 new followers" in message
        assert "100 total" in message

    def test_reports_negative_delta(self):
        with mock.patch.object(followers, "fetch_stats", return_value={"followers_count": 100}):
            with mock.patch.object(followers.state_gist, "read", return_value={"followers_count": 110}):
                with mock.patch.object(followers.state_gist, "write"):
                    with mock.patch.object(followers, "send") as mock_send:
                        followers.run()
        message = mock_send.call_args[0][0]
        assert "-10 new followers" in message


class TestStateGist:
    def test_read_raises_without_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="GITHUB_GIST_TOKEN"):
                state_gist.read()

    def test_read_returns_none_when_no_gist_found(self):
        with mock.patch.dict(os.environ, {"GITHUB_GIST_TOKEN": "tok"}):
            with mock.patch.object(state_gist, "GIST_ID", ""):
                with mock.patch.object(state_gist, "_find_gist_id", return_value=None):
                    assert state_gist.read() is None

    def test_read_returns_parsed_state(self):
        resp = mock.MagicMock()
        resp.json.return_value = {
            "files": {"notify-state.json": {"content": json.dumps({"followers_count": 42})}}
        }
        with mock.patch.dict(os.environ, {"GITHUB_GIST_TOKEN": "tok"}):
            with mock.patch.object(state_gist, "GIST_ID", "abc123"):
                with mock.patch.object(state_gist.requests, "get", return_value=resp):
                    state = state_gist.read()
        assert state == {"followers_count": 42}

    def test_read_returns_none_on_request_error(self):
        with mock.patch.dict(os.environ, {"GITHUB_GIST_TOKEN": "tok"}):
            with mock.patch.object(state_gist, "GIST_ID", "abc123"):
                with mock.patch.object(
                    state_gist.requests, "get", side_effect=requests.RequestException("boom")
                ):
                    assert state_gist.read() is None

    def test_write_raises_without_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="GITHUB_GIST_TOKEN"):
                state_gist.write({"followers_count": 1})

    def test_write_creates_gist_when_no_id(self):
        resp = mock.MagicMock()
        with mock.patch.dict(os.environ, {"GITHUB_GIST_TOKEN": "tok"}):
            with mock.patch.object(state_gist, "GIST_ID", ""):
                with mock.patch.object(state_gist, "_find_gist_id", return_value=None):
                    with mock.patch.object(state_gist.requests, "post", return_value=resp) as mock_post:
                        state_gist.write({"followers_count": 1})
        mock_post.assert_called_once()
        assert mock_post.call_args[1]["json"]["public"] is False

    def test_write_updates_existing_gist(self):
        resp = mock.MagicMock()
        with mock.patch.dict(os.environ, {"GITHUB_GIST_TOKEN": "tok"}):
            with mock.patch.object(state_gist, "GIST_ID", "abc123"):
                with mock.patch.object(state_gist.requests, "patch", return_value=resp) as mock_patch:
                    state_gist.write({"followers_count": 1})
        mock_patch.assert_called_once()


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

    def test_weekly_dispatches_to_followers(self):
        with mock.patch.object(notify_main.followers, "run") as mock_run:
            notify_main.main(["weekly"])
        mock_run.assert_called_once()

    def test_exits_nonzero_on_error(self):
        with mock.patch.object(notify_main.health, "run", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc:
                notify_main.main(["daily"])
        assert exc.value.code == 1
