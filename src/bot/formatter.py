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
    }

    for key, prefix in prefix_map.items():
        if key.lower() in full_name.lower():
            return prefix

    # Fallback: take first part before comma/og, shorten
    short = full_name.split(",")[0].split(" og ")[0].strip()
    return short


def _condense_or_truncate(text: str, header: str, body: str, limit: int | None = None) -> str:
    """Try LLM summarization first; fall back to truncation."""
    if limit is None:
        limit = POST_MAX_CHARS

    if LLM_ENABLED:
        try:
            from . import summarizer

            header_overhead = len(header) + 2  # +2 for \n\n
            max_body_chars = limit - header_overhead
            if max_body_chars > 40:
                condensed = summarizer.summarize(body, max_body_chars)
                if condensed:
                    result = f"{header}\n\n{condensed}"
                    if len(result) <= limit:
                        if len(result) + 3 <= limit:
                            result += "\n✨"
                        logger.info(
                            "LLM condensed body %d → %d chars",
                            len(body), len(condensed),
                        )
                        return result
                    logger.warning(
                        "LLM condensed body exceeds limit (%d chars > limit %d), truncating",
                        len(result), limit,
                    )
        except Exception:
            logger.exception("LLM summarization failed, falling back to truncation")

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
