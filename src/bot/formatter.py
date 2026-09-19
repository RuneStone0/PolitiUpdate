"""Format RSS items into X posts with truncation and LLM summarization."""

import logging
import re

from .config import POST_MAX_CHARS, LLM_ENABLED

logger = logging.getLogger(__name__)

RETWEET_PROMPT_SUFFIX = "\n\nDel gerne 🔁"
RETWEET_PROMPT_KEYWORDS = [
    "efterlysning", "savnet", "savner", "eftersøgning",
    "kontakt politiet", "har du set", "har du oplysninger",
    "man har oplysninger", "ring 114",
    "bedes du kontakte",
]


# Canonical district → short X prefix. Matched against the district name from
# the press-release page (src/bot/fetcher.py), which comes in several shapes:
#   "Midt- og Vestsjællands Politi"
#   "Anklagemyndigheden ved Midt- og Vestsjælland"   (prosecution messages)
#   "Anklagemyndigheden ved Sydøstjyllands Politi"
# So matching is stem-based (see _district_prefix): a key here is the district
# name lower-cased with a trailing " Politi" and a trailing genitive "s" removed.
# Order does not matter — the longest matching stem wins, so
# "københavns vestegn" beats "københavn".
DISTRICT_PREFIX_MAP = {
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

# Prosecution authorities wrap the district name; strip the wrapper before
# matching so "Anklagemyndigheden ved Midt- og Vestsjælland" resolves to the
# same prefix as "Midt- og Vestsjællands Politi". Longest wrapper first.
AUTHORITY_WRAPPERS = (
    "Anklagemyndigheden ved ",
    "Anklagemyndigheden ",
    "Statsadvokaten i ",
)

# Authorities that are not tied to a police district (no district stem to find).
AUTHORITY_PREFIX_MAP = {
    "statsadvokaten i viborg": "Statsadv. Viborg",
    "statsadvokaten i københavn": "Statsadv. København",
    "rigsadvokaten": "Rigsadvokaten",
    "anklagemyndigheden": "Anklagemyndigheden",
}

# Longest prefix a district fallback may produce before it is abbreviated.
MAX_FALLBACK_PREFIX_CHARS = 24

# Words that must never be the last token of a generated prefix — a prefix
# ending in "og"/"ved"/"-" is what produced the broken "Anklagemyndigheden
# ved Midt-:" header (17 tweets, Sept 2026).
DANGLING_TOKENS = {"og", "ved", "i", "for", "af", "til", "på", "den", "det", "-"}


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
    header = _build_header(title, district)
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


def _build_header(title: str, district: str) -> str:
    """Build the "<prefix>: <title>" header.

    The prefix is dropped when the title already names the district/authority
    — e.g. "Statsadvokaten i Viborg: Statsadvokaten i Viborg anker dom …" wasted
    25 of 280 characters and read as a stutter.
    """
    prefix = _district_prefix(district)
    if not prefix:
        return title

    title_lower = title.lower()
    if prefix.lower() in title_lower or district.strip().lower() in title_lower:
        return title

    return f"{prefix}: {title}"


def _district_stem(name: str) -> str:
    """Lower-cased match key: no trailing " Politi", no trailing genitive "s"."""
    stem = name.strip().lower()
    while stem.endswith(" politi"):
        stem = stem[: -len(" politi")].strip()
    if stem.endswith("s"):
        stem = stem[:-1]
    return stem


def _district_prefix(full_name: str) -> str:
    """Convert a full district/authority name to a short prefix, e.g.
    'Sydsjællands og Lolland-Falsters Politi' → 'Sydsjælland/L-F'
    'Anklagemyndigheden ved Midt- og Vestsjælland' → 'Midt/Vestsjælland'.

    Never returns a name cut mid-phrase: matching is done on whole district
    stems, and the fallback shortens at word boundaries and refuses to end on
    a conjunction or hyphen.
    """
    if not full_name or not full_name.strip():
        return ""

    name = full_name.strip()
    name_lower = name.lower()

    # 1. Exact canonical name.
    for key, prefix in DISTRICT_PREFIX_MAP.items():
        if key.lower() == name_lower:
            return prefix

    # 2. Exact authority name ("Statsadvokaten i Viborg", "Rigsadvokaten").
    if name_lower in AUTHORITY_PREFIX_MAP:
        return AUTHORITY_PREFIX_MAP[name_lower]

    # 3. Strip a prosecution-authority wrapper, then match the district part.
    #    Longest stem first so 'københavns vestegn' wins over 'københavn'.
    remainder = name
    for wrapper in AUTHORITY_WRAPPERS:
        if name_lower.startswith(wrapper.lower()):
            remainder = name[len(wrapper):].strip()
            break

    if remainder:
        remainder_lower = remainder.lower()
        for key, prefix in sorted(
            DISTRICT_PREFIX_MAP.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            if _district_stem(key) in _district_stem(remainder_lower):
                return prefix

        # 4. Wrapped authority with no police district of its own.
        if remainder_lower in AUTHORITY_PREFIX_MAP:
            return AUTHORITY_PREFIX_MAP[remainder_lower]

    # 5. Unknown district — shorten safely instead of cutting at " og ".
    return _fallback_prefix(remainder or name)


def _fallback_prefix(name: str) -> str:
    """Word-boundary-safe prefix for a district that isn't in the map.

    Joins the "X og Y" halves with "/" (dropping the conjunction) and shortens
    each half to fit, so the prefix can never end in "og", "ved" or "-".
    """
    clean = re.sub(r"\s*Politi\s*$", "", name.strip(), flags=re.IGNORECASE).strip()
    parts = [p.strip(" ,-") for p in re.split(r"\s+og\s+", clean)]
    parts = [p for p in parts if p]

    if not parts:
        return _strip_dangling(clean)

    budget = max(8, MAX_FALLBACK_PREFIX_CHARS // len(parts))
    short = "/".join(_abbreviate_part(p, budget) for p in parts)
    return _strip_dangling(short[:MAX_FALLBACK_PREFIX_CHARS])


def _abbreviate_part(part: str, budget: int) -> str:
    """Fit one half of a compound district name into `budget` characters.

    Hyphenated halves fall back to their initials ('Lolland-Falsters' → 'L-F');
    anything else is cut at a word boundary where one exists.
    """
    if len(part) <= budget:
        return part

    hyphen_words = [w for w in part.split("-") if w]
    if len(hyphen_words) > 1:
        initials = "-".join([hyphen_words[0]] + [w[0] for w in hyphen_words[1:]])
        if len(initials) <= budget:
            return initials

    words = part.split()
    if len(words) > 1:
        kept = ""
        for word in words:
            if kept and len(kept) + 1 + len(word) > budget:
                break
            kept = f"{kept} {word}".strip()
        if kept:
            return kept

    return part[:budget]


def _strip_dangling(text: str) -> str:
    """Drop trailing punctuation and conjunctions ("… Midt-", "… ved og")."""
    out = text.strip().rstrip(" ,-/")
    while True:
        head, sep, last = out.rpartition(" ")
        if sep and last.lower().strip(" ,-/") in DANGLING_TOKENS:
            out = head.strip().rstrip(" ,-/")
            continue
        return out



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
