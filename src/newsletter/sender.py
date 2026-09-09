"""Send a region's briefing to its subscribers via Brevo.

The Brevo REST integration is intentional but gated: in ``--dry-run`` it never
touches the network and just prints what it *would* send; otherwise it requires
a ``BREVO_API_KEY`` (and the account configured with a ``region`` contact
attribute). Real sending is wired once the account is set up — until then this
surfaces a clear error instead of failing silently.
"""

import logging

from . import config

logger = logging.getLogger(__name__)


def send_region(
    region_label: str,
    subscriber_emails: list[str],
    subject: str,
    text: str,
    dry_run: bool = False,
) -> dict:
    """Send (or, in dry-run, preview) a single region's briefing.

    If there are no subscribers, this is a no-op. In dry-run it returns the
    payload it would send without posting.
    """
    if not subscriber_emails:
        return {"region": region_label, "sent": 0, "dry_run": dry_run, "note": "no-subscribers"}

    if dry_run:
        logger.info("[dry-run] Would email %d subscriber(s) for %r: %s", len(subscriber_emails), region_label, subject)
        return {"region": region_label, "sent": len(subscriber_emails), "dry_run": True}

    if not config.BREVO_API_KEY:
        raise RuntimeError(
            "BREVO_API_KEY is not set — can't send region %r. Wire the Brevo account "
            "+ key, or run with --dry-run." % region_label
        )

    return _brevo_send(region_label, subscriber_emails, subject, text)


def _brevo_send(region_label: str, emails: list[str], subject: str, text: str) -> dict:
    """Placeholder for the real Brevo campaign/contacts send.

    To be implemented against the Brevo API once the account + ``region``
    attribute are configured: fetch this region's ``region``-tagged contacts,
    then dispatch a campaign (POST /v3/smtp/email for transactional, or the
    campaigns API). Return the result of the dispatch.
    """
    raise NotImplementedError(
        "Brevo dispatch not yet implemented — needs BREVO_API_KEY + a configured "
        "'region' contact attribute. Region %r, %d recipients, subject %r"
        % (region_label, len(emails), subject)
    )
