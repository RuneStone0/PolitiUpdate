"""Decide which briefing a subscriber gets — every state must map somewhere.

The public signup form can only target ONE Brevo list, and until a region
picker exists in Brevo's *form editor* it captures the e-mail address only, so
contacts arrive with an empty ``REGION`` attribute. Region list membership is
therefore derived from that attribute at send time
(``sender.sync_region_lists``).

The rule this module encodes: **every subscriber state maps to exactly one
briefing.** An empty or unrecognised ``REGION`` gets the country-wide briefing
(``REGION_NATIONAL`` = "Hele landet", which already doubles as the
"send me everything" label) — never silence.

Why this exists: with the region list mapping alone, a contact without a region
matched *no* list, so the weekly run sent them nothing at all, forever. The
funnel collected signups and delivered none of them; the defect was invisible
because a send needs an authenticated Brevo sender and had never run.
``tests/test_newsletter.py`` covers the mapping so it cannot regress.
"""

from src.common import regions as region_map


def briefing_region(region_value: str | None) -> str:
    """Return the region label whose briefing this subscriber receives.

    An empty, whitespace or unrecognised value falls back to the country-wide
    briefing rather than to nothing.
    """
    value = (region_value or "").strip()
    if value in region_map.REGIONS:
        return value
    return region_map.REGION_NATIONAL


def send_order() -> list[str]:
    """Return the briefing labels to send each week, country-wide last.

    The four regional briefings go first, then the country-wide one (which is
    the biggest, since it contains every release of the week).
    """
    return [*region_map.REGIONS, region_map.REGION_NATIONAL]
