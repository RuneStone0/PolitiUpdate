"""Generate a Danish weekly digest narrative via DeepSeek."""

import html
import json
import logging
import re

import requests

from . import config

logger = logging.getLogger(__name__)

X_TWEET_URL = "https://x.com/PolitiUpdate/status/{id}"

# Only these prefixes are valid picks for "notable" — missing_person/witness_appeal
# cases are already the narrative's main subject, so they're excluded there.
NOTABLE_PREFIXES = ("A", "O")

_MARKER_RE = re.compile(r"\{\{([A-Za-z]\d+)\|([^{}]+)\}\}")

SYSTEM_PROMPT = (
    "Du er redaktør for PolitiUpdate, et dansk nyhedsbrev der opsummerer ugens "
    "politimeddelelser. Du skriver præcise, faktabaserede resuméer på dansk. "
    "Skriv i en neutral, journalistisk tone.\n\n"
    "Du svarer ALTID med et JSON-objekt med to felter:\n"
    '  "narrative": et resumé på 3-5 sætninger.\n'
    '  "notable": en liste af 0-4 objekter med "id" og "summary" — andre bemærkelsesværdige '
    "sager fra ANHOLDELSER/SIGTELSER eller ØVRIGE SAGER (id'er der starter med A eller O), "
    "som fortjener en kort ekstra omtale ud over resuméet.\n\n"
    "REGLER FOR narrative:\n"
    "- Start altid med ugens vigtigste og mest interessante sager — efterlysninger og "
    "vidneappeller — nævnt ved navn. Fortsæt derefter kort med resten af ugens sager.\n"
    "- Hver gang du omtaler en KONKRET sag fra en af de id-mærkede lister nedenfor, "
    "skal omtalen markeres sådan: {{id|den tekst du skriver}} — fx "
    "\"{{M1|en 14-årig dreng fra Lunderskov}} blev efterlyst\". Brug KUN id'er fra "
    "listerne nedenfor, og marker kun konkrete enkeltsager — ikke sammenfatninger som "
    "\"105 meddelelser\" eller \"37 anholdelser\".\n"
    "- Bevar navne, aldre og steder i efterlysningssager — de er vigtige for læseren.\n"
    "- Undgå at specificere anholdelses- og sigtelsessager med navne i narrative-feltet.\n"
    "- Skriv KUN det faktiske resumé. Ingen introduktion, ingen overskrift, ingen kommentarer.\n"
    "- Brug korrekt dansk grammatik og tegnsætning. Undgå gentagelser og fyldord.\n\n"
    "REGLER FOR notable:\n"
    "- Vælg KUN sager der er reelt bemærkelsesværdige (usædvanlige, alvorlige eller af særlig "
    "offentlig interesse) — ikke rutinesager. Vælg 0 hvis ingen skiller sig ud, og maks. 4.\n"
    "- Nævn aldrig navne på sigtede, anholdte eller mistænkte personer — heller ikke i notable.\n"
    '- "id" SKAL være præcis et af de angivne id\'er, og skal starte med A eller O — '
    "opfind aldrig egne id'er.\n"
    '- "summary" er én kort, faktuel sætning på dansk.'
)


def _labeled_sections(posts_by_cat: dict) -> tuple[str, dict]:
    """Build an ID-tagged listing of every category's titles for the prompt.

    Returns (prompt text, lookup of id -> {title, x_post_id, category}) so the
    LLM's narrative markers and "notable" picks can be mapped back to a real
    post without relying on it reproducing a title verbatim.
    """
    lookup: dict[str, dict] = {}
    blocks = []
    for cat, prefix, heading in (
        ("missing_person", "M", "EFTERLYSNINGER/SAVNEDE"),
        ("witness_appeal", "W", "VIDNEAPPELLER"),
        ("arrest", "A", "ANHOLDELSER/SIGTELSER"),
        ("other", "O", "ØVRIGE SAGER"),
    ):
        posts = posts_by_cat.get(cat, [])
        if not posts:
            continue
        lines = []
        for i, post in enumerate(posts, start=1):
            cid = f"{prefix}{i}"
            lookup[cid] = {
                "title": post["title"],
                "x_post_id": post.get("x_post_id"),
                "category": cat,
            }
            lines.append(f"[{cid}] {post['title']}")
        blocks.append(f"{heading}:\n" + "\n".join(lines))
    return "\n\n".join(blocks), lookup


def _parse_response(raw: str) -> tuple[str, list]:
    """Parse the LLM's JSON reply, tolerating a stray ```json code fence."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("DeepSeek response was not valid JSON — using raw text as narrative")
        return raw.strip(), []

    if not isinstance(parsed, dict):
        return raw.strip(), []

    narrative = str(parsed.get("narrative", "")).strip()
    notable = parsed.get("notable", [])
    if not isinstance(notable, list):
        notable = []
    return narrative, notable


def _linkify(narrative: str, lookup: dict) -> tuple[str, str]:
    """Resolve {{id|text}} markers in the raw LLM narrative.

    Returns (plain, html): `plain` strips markers down to their inner text
    (safe for any plain-text consumer), `html` turns resolvable markers into
    <a> tags linking to the source tweet (falls back to escaped plain text
    for unknown ids or posts missing an x_post_id).
    """
    plain_parts = []
    html_parts = []
    pos = 0
    for m in _MARKER_RE.finditer(narrative):
        plain_parts.append(narrative[pos:m.start()])
        html_parts.append(html.escape(narrative[pos:m.start()]))

        cid, text = m.group(1), m.group(2)
        plain_parts.append(text)

        post = lookup.get(cid)
        if post and post.get("x_post_id"):
            url = X_TWEET_URL.format(id=post["x_post_id"])
            html_parts.append(
                f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(text)}</a>'
            )
        else:
            html_parts.append(html.escape(text))

        pos = m.end()

    plain_parts.append(narrative[pos:])
    html_parts.append(html.escape(narrative[pos:]))
    return "".join(plain_parts), "".join(html_parts)


def generate(data: dict) -> dict:
    """Generate the narrative + notable-case picks for the given week's data.

    Returns {"narrative": str, "narrative_html": str, "notable": [{"title",
    "summary", "category", "url"}]}. Raises RuntimeError if the LLM call
    fails or returns no usable narrative.
    """
    if not config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set — cannot generate digest narrative.")

    week = data["week"]
    year = data["year"]
    total = data["total_posts"]
    posts_by_cat = data["posts_by_category"]

    content_summary, lookup = _labeled_sections(posts_by_cat)

    user_prompt = (
        f"Skriv et ugeoverblik for uge {week}, {year}. "
        f"Politiet udsendte {total} meddelelser i alt.\n\n"
        f"{content_summary}\n\n"
        "Svar udelukkende med JSON på formen "
        '{"narrative": "...", "notable": [{"id": "...", "summary": "..."}]}.'
    )

    try:
        resp = requests.post(
            f"{config.LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {config.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 800,
                "response_format": {"type": "json_object"},
            },
            timeout=config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"DeepSeek API request failed: {e}") from e

    try:
        raw_content = resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Failed to parse DeepSeek response: {e}") from e

    raw_narrative, notable_raw = _parse_response(raw_content)
    if not raw_narrative:
        raise RuntimeError("DeepSeek response did not include a usable narrative.")

    narrative, narrative_html = _linkify(raw_narrative, lookup)

    notable = []
    for item in notable_raw:
        if not isinstance(item, dict):
            continue
        cid = item.get("id")
        if not isinstance(cid, str) or not cid.startswith(NOTABLE_PREFIXES):
            continue
        post = lookup.get(cid)
        summary = str(item.get("summary", "")).strip()
        if not post or not summary or not post.get("x_post_id"):
            continue
        notable.append(
            {
                "title": post["title"],
                "summary": summary,
                "category": post["category"],
                "url": X_TWEET_URL.format(id=post["x_post_id"]),
            }
        )

    logger.info(
        "Generated digest narrative (%d chars, %d notable extras)", len(narrative), len(notable)
    )
    return {"narrative": narrative, "narrative_html": narrative_html, "notable": notable}
