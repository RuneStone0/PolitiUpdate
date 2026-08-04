"""Background HTTP server exposing a /health endpoint for Docker health checks.

Runs on a daemon thread. Checks database connectivity, RSS feed reachability,
process uptime, and time since the last successful poll cycle.
"""

import http.server
import json
import logging
import threading
import time

import requests

from . import db
from .config import RSS_FEED_URL

logger = logging.getLogger(__name__)

_start_time = time.time()
_last_poll: float = 0.0
_server: http.server.HTTPServer | None = None


def set_last_poll() -> None:
    """Record that a poll cycle just completed successfully."""
    global _last_poll
    _last_poll = time.time()


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default access logging

    def do_GET(self):
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return

        checks: dict[str, str] = {}
        healthy = True

        # DB: simple connectivity check
        try:
            conn = db.get_conn()
            conn.execute("SELECT 1")
            conn.close()
            checks["db"] = "ok"
        except Exception as e:
            checks["db"] = str(e)
            healthy = False

        # RSS: verify the host is reachable (HEAD request)
        try:
            resp = requests.head(RSS_FEED_URL, timeout=10)
            checks["rss"] = f"reachable ({resp.status_code})"
        except Exception as e:
            checks["rss"] = str(e)
            healthy = False

        # Activity
        checks["uptime_seconds"] = int(time.time() - _start_time)
        if _last_poll:
            checks["seconds_since_last_poll"] = int(time.time() - _last_poll)
        else:
            checks["seconds_since_last_poll"] = None

        status = 200 if healthy else 503
        body = json.dumps({"healthy": healthy, "checks": checks})

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())


def start(port: int = 8080) -> None:
    """Start the health HTTP server on a background daemon thread."""
    global _server
    _server = http.server.HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=_server.serve_forever, name="health", daemon=True)
    thread.start()
    logger.info("Health endpoint listening on port %d", port)


def stop() -> None:
    """Shut down the health server (for testing)."""
    global _server
    if _server:
        _server.shutdown()
        _server = None
