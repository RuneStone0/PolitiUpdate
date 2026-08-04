"""Tests for health.py — the /health endpoint."""

import os
import sys
import threading
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import urllib.request
import urllib.error

import pytest

import src.bot.health as health
import src.bot.config as config


@pytest.fixture(autouse=True)
def stop_server():
    """Ensure health server is stopped after each test."""
    yield
    health.stop()


def _get_health(port: int = 9876) -> tuple[int, dict]:
    """Fetch /health and return (status_code, parsed_json)."""
    import json

    url = f"http://localhost:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class TestHealthEndpoint:
    def test_returns_200_when_healthy(self):
        health.start(port=9876)
        time.sleep(0.1)

        status, data = _get_health(9876)
        assert status == 200
        assert data["healthy"] is True
        assert data["checks"]["db"] == "ok"
        assert "reachable" in data["checks"]["rss"]

    def test_includes_uptime(self):
        health.start(port=9877)
        time.sleep(0.1)

        _, data = _get_health(9877)
        assert data["checks"]["uptime_seconds"] >= 0

    def test_includes_seconds_since_last_poll(self):
        health.start(port=9878)
        health.set_last_poll()
        time.sleep(0.1)

        _, data = _get_health(9878)
        assert data["checks"]["seconds_since_last_poll"] >= 0

    def test_returns_503_when_db_unavailable(self):
        with mock.patch("src.bot.health.db.get_conn") as mock_conn:
            mock_conn.side_effect = RuntimeError("db down")
            health.start(port=9879)
            time.sleep(0.1)

            status, data = _get_health(9879)
            assert status == 503
            assert data["healthy"] is False
            assert data["checks"]["db"] != "ok"

    def test_returns_503_when_rss_unreachable(self):
        with mock.patch("src.bot.health.requests.head") as mock_head:
            mock_head.side_effect = OSError("DNS failure")
            health.start(port=9880)
            time.sleep(0.1)

            status, data = _get_health(9880)
            assert status == 503
            assert data["healthy"] is False
            assert "DNS failure" in data["checks"]["rss"]

    def test_returns_404_for_other_paths(self):
        health.start(port=9881)
        time.sleep(0.1)

        status, _ = _get_health(9881)
        assert status == 200

        try:
            urllib.request.urlopen("http://localhost:9881/other", timeout=5)
        except urllib.error.HTTPError as e:
            assert e.code == 404

    def test_server_runs_on_daemon_thread(self):
        health.start(port=9882)
        time.sleep(0.1)

        # Find the health thread
        threads = [t for t in threading.enumerate() if t.name == "health"]
        assert len(threads) == 1
        assert threads[0].daemon

    def test_set_last_poll_updates_timestamp(self):
        health.start(port=9883)
        time.sleep(0.4)  # ensure measurable difference
        health.set_last_poll()
        time.sleep(0.1)

        _, data = _get_health(9883)
        assert data["checks"]["seconds_since_last_poll"] <= 1
        assert data["checks"]["uptime_seconds"] >= 0
