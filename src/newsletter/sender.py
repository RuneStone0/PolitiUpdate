"""Send a region's briefing to its subscribers via Brevo.

The Brevo REST integration is gated: in ``--dry-run`` it never touches the
network and just prints what it *would* send; otherwise it requires a
``BREVO_API_KEY`` and an authenticated ``BREVO_SENDER_EMAIL`` (a verified
sending domain). Until then it surfaces a clear error instead of failing
silently.

Sender details (Brevo v3 API):
- ``fetch_region_contacts`` pulls a region's subscribers via
  ``GET /v3/contacts`` filtered on the region contact attribute (documented
  ``equals(ATTRIBUTE,"value")`` filter syntax).
- ``_brevo_send`` dispatches ONE transactional email per subscriber via
  ``POST /v3/smtp/email`` — one call per recipient so no subscriber's address
  is exposed to the others (GDPR-safe), and well within the free plan's
  300 emails/day.
"""

import logging

import requests

from . import config

logger = logging.getLogger(__name__)

BREVO_API = "https://api.brevo.com/v3"
CONTACTS_PAGE_LIMIT = 1000


def _headers() -> dict:
    return {
        "api-key": config.BREVO_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


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
        logger.info(
            "[dry-run] Would email %d subscriber(s) for %r: %s",
            len(subscriber_emails), region_label, subject,
        )
        return {"region": region_label, "sent": len(subscriber_emails), "dry_run": True}

    if not config.BREVO_API_KEY:
        raise RuntimeError(
            "BREVO_API_KEY is not set — can't send region %r. Wire the Brevo account "
            "+ key, or run with --dry-run." % region_label
        )
    if not config.BREVO_SENDER_EMAIL:
        raise RuntimeError(
            "BREVO_SENDER_EMAIL is not set — can't send region %r. Set the authenticated "
            "sender address (e.g. nyhedsbrev@mail.politiupdate.com)." % region_label
        )

    return _brevo_send(region_label, subscriber_emails, subject, text)


def _brevo_send(region_label: str, emails: list[str], subject: str, text: str) -> dict:
    """Dispatch one transactional email per subscriber via Brevo.

    One ``POST /v3/smtp/email`` call per recipient keeps each subscriber's
    address private (no cross-recipient exposure in the To header). Returns the
    collected message IDs.
    """
    message_ids: list[str] = []
    for email in emails:
        payload = {
            "sender": {
                "name": config.BREVO_SENDER_NAME,
                "email": config.BREVO_SENDER_EMAIL,
            },
            "to": [{"email": email}],
            "subject": subject,
            "textContent": text,
        }
        resp = requests.post(
            f"{BREVO_API}/smtp/email",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        message_ids.append(data.get("messageId") or data.get("messageIds"))

    logger.info("Sent %d email(s) for region %r", len(emails), region_label)
    return {"region": region_label, "sent": len(emails), "message_ids": message_ids}


def fetch_region_contacts(region_label: str) -> list[str]:
    """Return the subscriber email addresses for a region.

    Queries ``GET /v3/contacts`` with the documented ``equals`` filter on the
    region contact attribute (e.g. ``equals(REGION,"Jylland")``), paginating
    through the full result set.
    """
    if not config.BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not set — can't fetch region contacts.")

    emails: list[str] = []
    offset = 0
    while True:
        resp = requests.get(
            f"{BREVO_API}/contacts",
            headers=_headers(),
            params={
                "limit": CONTACTS_PAGE_LIMIT,
                "offset": offset,
                "filter": 'equals(%s,"%s")' % (config.BREVO_REGION_ATTRIBUTE, region_label),
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        contacts = data.get("contacts", [])
        for contact in contacts:
            email = contact.get("email")
            if email:
                emails.append(email)
        count = data.get("count", len(contacts))
        offset += len(contacts)
        if not contacts or offset >= count:
            break

    logger.info("Fetched %d subscriber(s) for region %r", len(emails), region_label)
    return emails
