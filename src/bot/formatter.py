"""Format RSS items into X posts with truncation and LLM summarization."""

import logging

from .config import POST_MAX_CHARS, LLM_ENABLED

logger = logging.getLogger(__name__)

RETWEET_PROMPT_SUFFIX = "\n\nDel gerne 🔁"
RETWEET_PROMPT_KEYWORDS = [
    "efterlysning", "savnet", "savner", "eftersøgning",
    "kontakt politiet", "har du set", "har du oplysninger",
    "man har oplysninger", "ring 114",
    "bedes du kontakte",
]


def format_post(title: str, district: str, body: str) -> str:
    """Format a post for X.

    Format:
        <district prefix>: <title>

        <body text>

    District prefix is a short tag derived from the full district name.
    If the post exceeds POST_MAX_CHARS and LLM_ENABLED is set, the body
    is condensed via DeepSeek instead of hard-truncated.

    Posts with public-help keywords (efterlysning, savnet, etc.)
    get a "Del gerne 🔁" suffix appended after truncation/condensation
    so it never gets cut.
    """
    prefix = _district_prefix(district)
    header = f"{prefix}: {title}" if prefix else title
    retweet = RETWEET_PROMPT_SUFFIX if _should_retweet_prompt(body) else ""

    if body:
        text = f"{header}\n\n{body}"
    else:
        text = header

    if POST_MAX_CHARS > 0 and len(text) + len(retweet) > POST_MAX_CHARS:
        limit = POST_MAX_CHARS - len(retweet)
        text = _condense_or_truncate(text, header, body, limit)

    if retweet:
        text += retweet

    return text


def _should_retweet_prompt(body: str) -> bool:
    """Check if body text indicates police are asking the public for help."""
    body_lower = body.lower()
    return any(kw in body_lower for kw in RETWEET_PROMPT_KEYWORDS)


def _district_prefix(full_name: str) -> str:
    """Convert a full district name to a short prefix, e.g.
    'Sydsjællands og Lolland-Falsters Politi' → 'Sydsjælland/L-F'.
    """
    if not full_name:
        return ""

    prefix_map = {
        "Bornholms Politi": "Bornholm",
        "Fyns Politi": "Fyn",
        "Københavns Politi": "København",
        "Københavns Vestegns Politi": "Kbh Vestegn",
        "Midt- og Vestjyllands Politi": "Midt/Vestjylland",
        "Midt- og Vestsjællands Politi": "Midt/Vestsjælland",
        "National enhed for Særlig Kriminalitet": "NSK",
        "Nordjyllands Politi": "Nordjylland",
        "Nordsjællands Politi": "Nordsjælland",
        "Syd- og Sønderjyllands Politi": "Sydjylland",
        "Sydøstjyllands Politi": "Sydøstjylland",
        "Sydsjællands og Lolland-Falsters Politi": "Sydsjælland/L-F",
        "Østjyllands Politi": "Østjylland",
        "Rigspolitiet": "Rigspolitiet",
        "Politiskolen": "Politiskolen",
    }

    for key, prefix in prefix_map.items():
        if key.lower() in full_name.lower():
            return prefix

    # Fallback: take first part before comma/og, shorten
    short = full_name.split(",")[0].split(" og ")[0].strip()
    return short


MAX_CONDENSE_ATTEMPTS = 3

# DeepSeek is unreliable at hitting an exact character budget and tends to
# overshoot rather than undershoot — this is subtracted from the true
# available budget before the first condense attempt, so typical overshoot
# still lands under the real limit. See _condense_or_truncate() below.
CONDENSE_SAFETY_MARGIN = 50


def _condense_or_truncate(text: str, header: str, body: str, limit: int | None = None) -> str:
    """Try LLM summarization first, retrying with a tighter target if the
    condensed result still overshoots the limit; fall back to truncation."""
    if limit is None:
        limit = POST_MAX_CHARS

    if LLM_ENABLED:
        try:
            from . import summarizer

            header_overhead = len(header) + 2  # +2 for \n\n
            available = limit - header_overhead
            if available > 40:
                # DeepSeek reliably overshoots a requested character budget
                # rather than undershooting it (measured mean/median
                # overshoot ~50-57 chars in prod on 2026-08-22) — likely
                # because the system prompt's "preserve ALL facts"
                # instruction is in tension with a hard length cap. Asking
                # for less than the true available budget up front absorbs
                # that typical overshoot, so the first attempt fits without
                # needing the retry loop below. The >40 gate above is
                # deliberately checked against the unadjusted `available`
                # space, not this margin-reduced target, so a tight-but-
                # workable header/limit combo still gets an LLM attempt
                # instead of being skipped straight to truncation.
                target = max(20, available - CONDENSE_SAFETY_MARGIN)
                for attempt in range(1, MAX_CONDENSE_ATTEMPTS + 1):
                    condensed = summarizer.summarize(body, target)
                    if not condensed:
                        break
                    result = f"{header}\n\n{condensed}"
                    if len(result) <= limit:
                        logger.info(
                            "LLM condensed body %d → %d chars (attempt %d)",
                            len(body), len(condensed), attempt,
                        )
                        return result
                    overflow = len(result) - limit
                    logger.warning(
                        "LLM condensed body exceeds limit (attempt %d/%d): "
                        "%d chars > limit %d, retrying tighter",
                        attempt, MAX_CONDENSE_ATTEMPTS, len(result), limit,
                    )
                    target = max(20, target - overflow - 10)
                else:
                    # Loop ran out of attempts without ever fitting (as
                    # opposed to the `break` above, when DeepSeek itself
                    # failed — that's already logged in summarizer.py).
                    # Previously silent; flagged so the effect of
                    # CONDENSE_SAFETY_MARGIN on this rate is measurable.
                    logger.warning(
                        "LLM condensation exhausted %d attempts, falling back to "
                        "truncation for %r",
                        MAX_CONDENSE_ATTEMPTS, header,
                    )
        except Exception:
            logger.exception(
                "LLM summarization failed, falling back to truncation for %r", header
            )

    return _truncate(text, limit)


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text at nearest sentence or word boundary, adding …"""
    if len(text) <= max_chars:
        return text

    truncated = text[: max_chars - 1]  # leave room for …

    # Cut at last sentence boundary (period/exclamation/question + space)
    for delim in (". ", "! ", "? "):
        idx = truncated.rfind(delim)
        if idx > max_chars // 4:
            return truncated[: idx + 1] + "…"

    # Cut at last space
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 4:
        return truncated[:last_space] + "…"

    # Last resort: hard cut
    return truncated[: max_chars - 1] + "…"
