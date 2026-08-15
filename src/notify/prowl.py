"""Send notifications via the Prowl webhook."""

import logging

import requests

from . import config

logger = logging.getLogger(__name__)


def send(message: str) -> bool:
    """POST a message to the Prowl webhook.

    Returns True on success. Failures are logged and swallowed rather than
    raised — a broken notification channel shouldn't crash the caller (e.g.
    a bot posting failure that's trying to *report itself* via this path).
    """
    if not config.PROWL_WEBHOOK_URL:
        logger.warning("PROWL_WEBHOOK_URL is not set — dropping notification: %s", message)
        return False
    try:
        resp = requests.post(
            config.PROWL_WEBHOOK_URL,
            json={"message": message},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException:
        logger.exception("Failed to send Prowl notification")
        return False
