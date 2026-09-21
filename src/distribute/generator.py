"""Build paste-ready Danish drafts for the manual distribution channels.

Why this exists
---------------
Distribution — not pipeline — is PolitiUpdate's binding constraint
(``docs/growth/distribution-playbook.md``): 27 X followers, and Reddit/Danish
communities are the only real reach lever. But Reddit is **manual** (Reddit
closed self-service API app creation, so no bot can post) — and a manual
channel dies if every week costs a writing session. This module turns the
published weekly digest into ready-to-paste text for each channel, so posting
is a copy/paste plus a reply session.

Honesty gate
------------
The drafts must never claim a completeness we do not deliver: production runs
``X_PRO`` unset (``POST_MAX_CHARS=280``, ``LLM_ENABLED=1``), so ~68% of
releases are LLM-condensed rather than mirrored verbatim (verified against the
live container + prod DB; see ``docs/PLAN.md`` → "Full-message posts are NOT
live"). :func:`assert_honest` therefore fails fast if a template ever claims
"fuld tekst"/"komplet" while that is untrue.
"""

from urllib.parse import urlencode

from src.common.regions import (
    REGION_FYN,
    REGION_HOVEDSTADEN,
    REGION_JYLLAND,
    REGION_SJAELLAND,
)

CATEGORY_LABELS = {
    "missing_person": "Efterlysninger/savnede",
    "witness_appeal": "Vidneappeller",
    "arrest": "Anholdelser/sigtelser",
    "other": "Øvrige sager",
}

# The four user-facing regions (mirrors src/common/regions.REGIONS) plus the
# canonical display order used for the regional drafts.
REGION_ORDER = [REGION_HOVEDSTADEN, REGION_SJAELLAND, REGION_JYLLAND, REGION_FYN]

# Published region labels (posts.district short labels) → the 4 regions above.
# Ordered: "Nordsjælland" must resolve to Hovedstaden before the "Sjælland"
# rule can match it, and "Sydsjælland/L-F" must land in Sjælland.
_LABEL_REGION_RULES = (
    ("københavn", REGION_HOVEDSTADEN),
    ("kbh", REGION_HOVEDSTADEN),
    ("vestegn", REGION_HOVEDSTADEN),
    ("nordsjælland", REGION_HOVEDSTADEN),
    ("bornholm", REGION_HOVEDSTADEN),
    ("sjælland", REGION_SJAELLAND),
    ("lolland", REGION_SJAELLAND),
    ("l-f", REGION_SJAELLAND),
    ("jylland", REGION_JYLLAND),
    ("fyn", REGION_FYN),
)

HONESTY_DISCLAIMER = (
    "Kilde: politiets egen RSS-feed (via Ritzau). Uofficielt projekt uden "
    "tilknytning til politiet."
)

# Claims that are false while X_PRO is unset in production (see module docstring).
FORBIDDEN_CLAIMS = (
    "fuld tekst",
    "fulde tekst",
    "fuldstændig",
    "komplet",
    "hele meddelelsen",
    "ordret",
    "1:1",
)

X_MAX_CHARS = 280


class DishonestCopyError(ValueError):
    """Raised when a draft makes a completeness claim we cannot deliver."""


def assert_honest(text: str) -> str:
    """Return *text*, raising if it contains a claim we can't stand behind."""
    lowered = text.lower()
    for claim in FORBIDDEN_CLAIMS:
        if claim in lowered:
            raise DishonestCopyError(
                f"draft claims '{claim}' — production runs POST_MAX_CHARS=280 with "
                "LLM condensation, so completeness claims are untrue today"
            )
    return text


def utm_link(url: str, source: str, campaign: str, medium: str = "social") -> str:
    """Append UTM params so the first channel that works is attributable."""
    sep = "&" if "?" in url else "?"
    query = urlencode(
        {"utm_source": source, "utm_medium": medium, "utm_campaign": campaign}
    )
    return f"{url}{sep}{query}"


def category_lines(digest: dict) -> list[str]:
    """``- Efterlysninger/savnede: 4``-style lines for every non-zero category."""
    counts = digest.get("categories") or {}
    lines = []
    for key, label in CATEGORY_LABELS.items():
        count = counts.get(key)
        if count:
            lines.append(f"- {label}: {count}")
    return lines


def region_label_to_region(label: str) -> str | None:
    """Map a published district label to one of the 4 regions (or ``None``)."""
    needle = (label or "").lower()
    for token, region in _LABEL_REGION_RULES:
        if token in needle:
            return region
    return None


def region_items(digest: dict, region: str) -> list[dict]:
    """Flatten the published ``region_items`` belonging to *region*."""
    grouped: list[dict] = []
    for label, items in (digest.get("region_items") or {}).items():
        if region_label_to_region(label) == region:
            grouped.extend(items or [])
    return grouped


def region_with_most_items(digest: dict) -> str | None:
    """Pick the region with the most published items (default for FB drafts)."""
    best, best_count = None, -1
    for region in REGION_ORDER:
        count = len(region_items(digest, region))
        if count > best_count:
            best, best_count = region, count
    return best if best_count > 0 else None


def _notable_bullets(digest: dict, limit: int = 4) -> list[str]:
    bullets = []
    for pick in (digest.get("notable") or [])[:limit]:
        title = (pick.get("title") or "").strip()
        summary = (pick.get("summary") or "").strip()
        if not title:
            continue
        bullets.append(f"- **{title}**" + (f" — {summary}" if summary else ""))
    return bullets


def _header(channel: str, digest: dict, notes: list[str]) -> str:
    """HTML-comment header with channel + posting instructions (invisible when pasted)."""
    lines = [
        f"PolitiUpdate channel kit · {channel} · uge {digest['week']}/{digest['year']}",
        "",
        *notes,
    ]
    body = "\n".join(lines)
    return f"<!--\n{body}\n-->\n"


def build_reddit_post(digest: dict, site_base: str) -> str:
    """r/Denmark self-post: real content + one tagged archive link."""
    link = utm_link(
        f"{site_base.rstrip('/')}/uge/{digest['year']}/{digest['week']}/",
        source="reddit",
        campaign=f"uge{digest['week']}",
    )
    parts = [
        _header(
            "Reddit self-post (r/Denmark, r/danmark)",
            digest,
            [
                "Post som SELVPOST med indhold — aldrig et bart link.",
                "r/Denmark regel 5 (selvpromovering): modmail FØRST, derefter denne post.",
                "Svar på kommentarer samme dag; log push-vinduet i data/growth_metrics.jsonl.",
            ],
        ),
        f"**Ugens overblik: {digest['total_posts']} meddelelser fra politiet i uge "
        f"{digest['week']}**",
        "",
    ]
    narrative = (digest.get("narrative") or "").strip()
    if narrative:
        parts += [narrative, ""]
    counts = category_lines(digest)
    if counts:
        parts += ["Ugens tal:", *counts, ""]
    bullets = _notable_bullets(digest)
    if bullets:
        parts += ["Ugens bemærkelsesværdige sager:", *bullets, ""]
    parts += [
        "Politiet lukkede deres egne opslag på X, men publicerer fortsat alt via deres "
        "officielle RSS-feed. Overblikket her er samlet fra den åbne kilde.",
        "",
        f"Ugens overblik opdelt på distrikt og kategori: {link}",
        "",
        HONESTY_DISCLAIMER,
    ]
    return assert_honest("\n".join(parts))


def build_facebook_post(digest: dict, site_base: str, region: str) -> str:
    """Regional Facebook-group post — one region, never the national digest."""
    items = region_items(digest, region)
    link = utm_link(
        f"{site_base.rstrip('/')}/uge/{digest['year']}/{digest['week']}/",
        source="facebook",
        campaign=f"uge{digest['week']}-{region.lower()}",
    )
    parts = [
        _header(
            f"Facebook-gruppe ({region})",
            digest,
            [
                "Læs gruppens regler først (mange forbyder links — læg linket i en kommentar).",
                "Maks. én post pr. gruppe pr. uge.",
                f"Region: {region} · {len(items)} meddelelser i ugen ifølge arkivet.",
            ],
        ),
        f"Ugens politikort for {region}: politiet har haft {len(items)} "
        f"opdatering{'er' if len(items) != 1 else ''} i uge {digest['week']}.",
        "",
    ]
    titles = [i.get("title", "").strip() for i in items if i.get("title")][:5]
    if titles:
        parts += ["Blandt andet:", *[f"- {t}" for t in titles], ""]
    parts += [
        f"Jeg har samlet ugens meddelelser her: {link}",
        "",
        HONESTY_DISCLAIMER,
    ]
    return assert_honest("\n".join(parts))


def build_x_post(digest: dict, site_base: str = "") -> str:
    """Link-free X post draft (≤280 chars) — no URL surcharge, no link dependency.

    *site_base* is accepted for symmetry with the other builders but unused:
    X's free-tier link policy ($0.20/post) plus the honesty gate mean the X
    draft points readers at the profile, not at a URL.
    """
    notable = (digest.get("notable") or [{}])[0]
    headline = (notable.get("title") or "").strip()
    base = (
        f"Ugens sag i uge {digest['week']}: {headline}. "
        f"Alle politiets meddelelser ({digest['total_posts']} i alt) samles løbende her på "
        "profilen → @PolitiUpdate"
    )
    if len(base) > X_MAX_CHARS:
        budget = X_MAX_CHARS - len(base) + len(headline) - 1
        base = base.replace(headline, headline[: max(budget - 3, 0)].rstrip() + "…")
    if len(base) > X_MAX_CHARS:
        base = base[: X_MAX_CHARS - 1].rstrip() + "…"
    return assert_honest(base)


def build_summary(digest: dict, site_base: str) -> dict:
    """Machine-readable kit summary (for the metrics log / push-window record)."""
    return {
        "year": digest["year"],
        "week": digest["week"],
        "total_posts": digest["total_posts"],
        "categories": digest.get("categories", {}),
        "notable": [p.get("title") for p in (digest.get("notable") or [])],
        "generated_at": digest.get("generated_at"),
        "archive_url": f"{site_base.rstrip('/')}/uge/{digest['year']}/{digest['week']}/",
        "tagged_urls": {
            "reddit": utm_link(
                f"{site_base.rstrip('/')}/uge/{digest['year']}/{digest['week']}/",
                "reddit",
                f"uge{digest['week']}",
            ),
            "facebook": utm_link(
                f"{site_base.rstrip('/')}/uge/{digest['year']}/{digest['week']}/",
                "facebook",
                f"uge{digest['week']}",
            ),
        },
    }
