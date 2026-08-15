"""Logging handler that forwards ERROR+ log records to the Prowl webhook.

Attach to a long-running service's root logger (see bot/main.py) to get
near-real-time alerts on caught exceptions and error-level logs — e.g. the
bot's RSS-fetch and item-processing error handlers — without needing a
separate poller. Rate-limited per distinct error to avoid flooding Prowl
during a sustained outage (the bot logs the same error every poll).
"""

import logging
import time

from . import config
from .prowl import send

# Never forward records from this package's own loggers: prowl.send()'s
# failure path logs via logger.exception(), and if that were re-forwarded
# through this same handler it would recurse into send() indefinitely.
_EXCLUDED_PREFIX = "src.notify"


class ProwlErrorHandler(logging.Handler):
    def __init__(self, min_interval_seconds: int | None = None, level: int = logging.ERROR):
        super().__init__(level=level)
        self._min_interval = (
            config.ERROR_ALERT_MIN_INTERVAL if min_interval_seconds is None else min_interval_seconds
        )
        self._last_sent: dict[str, float] = {}

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == _EXCLUDED_PREFIX or record.name.startswith(_EXCLUDED_PREFIX + "."):
            return
        try:
            text = record.getMessage()
            if record.exc_info and record.exc_info[1]:
                exc_type = record.exc_info[0].__name__ if record.exc_info[0] else "Error"
                text = f"{text} ({exc_type}: {record.exc_info[1]})"

            key = f"{record.name}:{text}"
            now = time.time()
            if now - self._last_sent.get(key, 0.0) < self._min_interval:
                return
            self._last_sent[key] = now

            send(f"PolitiUpdate error [{record.name}]: {text}"[:1000])
        except Exception:
            pass  # a broken alert path must never break app logging


def install(min_interval_seconds: int | None = None, level: int = logging.ERROR) -> logging.Handler | None:
    """Attach a ProwlErrorHandler to the root logger if enabled via config.

    Idempotent — repeated calls (e.g. _setup_logging() running more than
    once) won't stack up duplicate handlers. Returns the handler (for
    tests/introspection), or None if disabled.
    """
    if not config.ERROR_ALERTS_ENABLED:
        return None
    root = logging.getLogger()
    for existing in root.handlers:
        if isinstance(existing, ProwlErrorHandler):
            return existing
    handler = ProwlErrorHandler(min_interval_seconds=min_interval_seconds, level=level)
    root.addHandler(handler)
    return handler
