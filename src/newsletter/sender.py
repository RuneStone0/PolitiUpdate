"""Send a region's briefing to its subscribers via Brevo *email campaigns*.

Why campaigns and not transactional email: a newsletter is consent-based
marketing, so every send must carry a working unsubscribe link + a
List-Unsubscribe header and should offer open/click stats. Brevo's
transactional ``POST /v3/smtp/email`` adds no unsubscribe footer, so it is the
wrong tool for a newsletter — campaigns are.

Flow per region:
1. ``sync_region_lists`` makes sure every contact whose ``REGION`` attribute
   equals the region is a member of that region's Brevo list. (The public
   signup form can only target one list, so membership is derived here from the
   attribute.)
2. ``send_region_campaign`` creates an email campaign targeting that list and
   sends it immediately (``POST /emailCampaigns`` -> ``POST /emailCampaigns/{id}/sendNow``).

Gated: in ``--dry-run`` nothing touches the network; a real send requires
``BREVO_API_KEY`` and an authenticated ``BREVO_SENDER_EMAIL``.
"""

import logging

import requests

from . import config

logger = logging.getLogger(__name__)

BREVO_API = "https://api.brevo.com/v3"
CONTACTS_PAGE_LIMIT = 1000
BATCH_CHUNK = 100  # Brevo's /contacts/batch accepts a limited batch per call


def _headers() -> dict:
    return {
        "api-key": config.BREVO_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def list_id_for_region(region_label: str) -> int | None:
    """Return the Brevo list id mapped to a region label (None if unmapped)."""
    return config.BREVO_REGION_LISTS.get(region_label)


def campaign_payload(
    region_label: str,
    subject: str,
    html: str,
    list_id: int,
    name: str | None = None,
) -> dict:
    """Build the ``POST /v3/emailCampaigns`` body for one region.

    The campaign targets exactly one region list. A custom unsubscribe page is
    attached when ``BREVO_UNSUB_PAGE_ID`` is set (otherwise Brevo's default
    unsubscribe page is used).
    """
    payload = {
        "name": name or f"PolitiUpdate - {region_label} - {subject}",
        "sender": {"name": config.BREVO_SENDER_NAME, "email": config.BREVO_SENDER_EMAIL},
        "subject": subject,
        "htmlContent": html,
        "recipients": {"listIds": [list_id]},
    }
    if config.BREVO_UNSUB_PAGE_ID:
        payload["unsubscriptionPageId"] = config.BREVO_UNSUB_PAGE_ID
    return payload


def send_region_campaign(
    region_label: str,
    subject: str,
    html: str,
    name: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Create + immediately send one region's campaign.

    In dry-run it returns what it *would* do and never touches the network.
    """
    list_id = list_id_for_region(region_label)
    if list_id is None:
        raise RuntimeError(
            "No Brevo list mapped for region %r — check BREVO_REGION_LISTS." % region_label
        )

    payload = campaign_payload(region_label, subject, html, list_id, name=name)

    if dry_run:
        logger.info(
            "[dry-run] Would create+send campaign %r -> list %s", payload["name"], list_id
        )
        return {"region": region_label, "list_id": list_id, "dry_run": True, "sent": False}

    if not config.BREVO_API_KEY:
        raise RuntimeError(
            "BREVO_API_KEY is not set — can't send region %r. Use --dry-run." % region_label
        )
    if not config.BREVO_SENDER_EMAIL:
        raise RuntimeError(
            "BREVO_SENDER_EMAIL is not set — can't send region %r. Set the authenticated "
            "sender address (e.g. nyhedsbrev@mail.politiupdate.com)." % region_label
        )

    created = requests.post(
        f"{BREVO_API}/emailCampaigns", headers=_headers(), json=payload, timeout=30
    )
    created.raise_for_status()
    campaign_id = created.json().get("id")

    sent = requests.post(
        f"{BREVO_API}/emailCampaigns/{campaign_id}/sendNow", headers=_headers(), timeout=30
    )
    sent.raise_for_status()

    logger.info("Campaign %s sent for region %r (list %s)", campaign_id, region_label, list_id)
    return {"region": region_label, "list_id": list_id, "campaign_id": campaign_id, "sent": True}


def fetch_region_contacts(region_label: str) -> list[str]:
    """Return the email addresses whose REGION attribute equals ``region_label``.

    Uses the documented ``equals(ATTRIBUTE,"value")`` filter on
    ``GET /v3/contacts``, paginating through the full result set.
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


def sync_region_lists(region_label: str, dry_run: bool = False) -> int:
    """Ensure every contact with ``REGION == region_label`` is in that region's list.

    Campaigns target lists, and the signup form only ever adds contacts to one
    list, so we map attribute -> list membership here before sending.
    Returns the number of contacts synced.
    """
    list_id = list_id_for_region(region_label)
    if list_id is None:
        raise RuntimeError("No Brevo list mapped for region %r." % region_label)

    emails = fetch_region_contacts(region_label)
    if not emails:
        return 0
    if dry_run:
        logger.info(
            "[dry-run] Would add %d contact(s) to list %s (%r)", len(emails), list_id, region_label
        )
        return len(emails)

    for start in range(0, len(emails), BATCH_CHUNK):
        chunk = emails[start:start + BATCH_CHUNK]
        resp = requests.post(
            f"{BREVO_API}/contacts/batch",
            headers=_headers(),
            json={"contacts": [{"email": e, "listIds": [list_id]} for e in chunk]},
            timeout=60,
        )
        resp.raise_for_status()

    logger.info("Synced %d contact(s) into list %s (%r)", len(emails), list_id, region_label)
    return len(emails)
