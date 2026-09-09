"""Shared police-district → region mapping.

Used by the newsletter (region-filtered weekly briefings) and the website
(region browse) to group a press release's ``district`` string into one of
four user-facing Danish regions plus a nationwide bucket.

The grouping matches the newsletter spec in ``docs/PLAN.md`` — a subscriber
picks one of four regions and national releases are auto-included everywhere:

- Hovedstaden: København, Københavns Vestegn, Nordsjælland, Bornholm
- Sjælland:    Midt/Vestsjælland, Sydsjælland/L-F
- Jylland:     Nordjylland, Midt/Vestjylland, Østjylland, Sydøstjylland, Sydjylland
- Fyn:         Fyn
- National:    Rigspolitiet, NSK, Politiskolen (included in every region)

Keep the district keys in sync with ``src.bot.formatter._district_prefix``,
which maps the same full district names to short X-post prefixes.
"""

# User-facing region labels (Danish). ``REGIONS`` is the canonical display
# order for signup forms / filtering and deliberately excludes the nationwide
# sentinel below.
REGION_HOVEDSTADEN = "Hovedstaden"
REGION_SJAELLAND = "Sjælland"
REGION_JYLLAND = "Jylland"
REGION_FYN = "Fyn"

# Nationwide entities that don't belong to a single region. Doubles as the
# subscriber opt-out "send me everything" label.
REGION_NATIONAL = "Hele landet"

REGIONS = [
    REGION_HOVEDSTADEN,
    REGION_SJAELLAND,
    REGION_JYLLAND,
    REGION_FYN,
]

# Full police district name → region. Keys are substring-matched
# (case-insensitive) against the DB ``district`` column, so prefixed variants
# such as "Anklagemyndigheden ved Østjyllands Politi" resolve to the same
# region as the bare district.
DISTRICT_TO_REGION = {
    # Hovedstaden (Copenhagen metro + North Zealand + Bornholm)
    "Københavns Politi": REGION_HOVEDSTADEN,
    "Københavns Vestegns Politi": REGION_HOVEDSTADEN,
    "Nordsjællands Politi": REGION_HOVEDSTADEN,
    "Bornholms Politi": REGION_HOVEDSTADEN,
    # Sjælland (rest of Zealand)
    "Midt- og Vestsjællands Politi": REGION_SJAELLAND,
    "Sydsjællands og Lolland-Falsters Politi": REGION_SJAELLAND,
    # Fyn (Funen)
    "Fyns Politi": REGION_FYN,
    # Jylland (all of Jutland — one bucket per the PLAN.md spec, so
    # Sydøstjyllands Politi's Midt-vs-Syddanmark straddle is moot)
    "Nordjyllands Politi": REGION_JYLLAND,
    "Midt- og Vestjyllands Politi": REGION_JYLLAND,
    "Østjyllands Politi": REGION_JYLLAND,
    "Sydøstjyllands Politi": REGION_JYLLAND,
    "Syd- og Sønderjyllands Politi": REGION_JYLLAND,
    # Nationwide
    "Rigspolitiet": REGION_NATIONAL,
    "National enhed for Særlig Kriminalitet": REGION_NATIONAL,
    "Politiskolen": REGION_NATIONAL,
}


def district_to_region(district: str) -> str | None:
    """Map a press-release ``district`` string to its region label.

    Returns ``None`` when the district can't be matched (the caller decides
    the fallback — e.g. treat as nationwide or skip).
    """
    if not district:
        return None
    needle = district.lower()
    # Longest key first, so overlapping keys can't shadow a more specific match.
    for key in sorted(DISTRICT_TO_REGION, key=len, reverse=True):
        if key.lower() in needle:
            return DISTRICT_TO_REGION[key]
    return None
