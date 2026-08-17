"""Generate a Danish weekly digest narrative via DeepSeek."""

import json
import logging

import requests

from . import config

logger = logging.getLogger(__name__)

X_TWEET_URL = "https://x.com/PolitiUpdate/status/{id}"

SYSTEM_PROMPT = (
    "Du er redaktør for PolitiUpdate, et dansk nyhedsbrev der opsummerer ugens "
    "politimeddelelser. Du skriver præcise, faktabaserede resuméer på dansk. "
    "Skriv i en neutral, journalistisk tone.\n\n"
    "Du svarer ALTID med et JSON-objekt med to felter:\n"
    '  "narrative": et resumé på 3-5 sætninger.\n'
    '  "notable": en liste af 0-4 objekter med "id" og "summary" — andre bemærkelsesværdige '
    "sager fra de id-mærkede lister nedenfor, som fortjener en kort ekstra omtale ud over "
    "resuméet.\n\n"
    "REGLER FOR narrative:\n"
    "- Start altid med ugens vigtigste og mest interessante sager — efterlysninger og "
    "vidneappeller — nævnt ved navn. Fortsæt derefter kort med resten af ugens sager.\n"
    "- Bevar navne, aldre og steder i efterlysningssager — de er vigtige for læseren.\n"
    "- Undgå at specificere anholdelses- og sigtelsessager med navne i narrative-feltet.\n"
    "- Skriv KUN det faktiske resumé. Ingen introduktion, ingen overskrift, ingen kommentarer.\n"
    "- Brug korrekt dansk grammatik og tegnsætning. Undgå gentagelser og fyldord.\n\n"
    "REGLER FOR notable:\n"
    "- Vælg KUN sager der er reelt bemærkelsesværdige (usædvanlige, alvorlige eller af særlig "
    "offentlig interesse) — ikke rutinesager. Vælg 0 hvis ingen skiller sig ud, og maks. 4.\n"
    "- Nævn aldrig navne på sigtede, anholdte eller mistænkte personer — heller ikke i notable.\n"
    '- "id" SKAL være præcis et af de angivne id\'er (fx "A3" eller "O7") — opfind aldrig egne id\'er.\n'
    '- "summary" er én kort, faktuel sætning på dansk.'
)


def _candidate_sections(posts_by_cat: dict) -> tuple[str, dict]:
    """Build an ID-tagged listing of arrest/other titles for the prompt.

    Returns (prompt text, lookup of id -> {title, x_post_id, category}) so the
    LLM's picks can be mapped back to a real post without relying on it
    reproducing a title verbatim.
    """
    lookup: dict[str, dict] = {}
    blocks = []
    for cat, prefix, heading in (
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


def generate(data: dict) -> dict:
    """Generate the narrative + notable-case picks for the given week's data.

    Returns {"narrative": str, "notable": [{"title", "summary", "category", "url"}]}.
    Raises RuntimeError if the LLM call fails or returns no usable narrative.
    """
    if not config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set — cannot generate digest narrative.")

    week = data["week"]
    year = data["year"]
    total = data["total_posts"]
    posts_by_cat = data["posts_by_category"]

    sections = []
    if posts_by_cat["missing_person"]:
        titles = [p["title"] for p in posts_by_cat["missing_person"]]
        sections.append("EFTERLYSNINGER/SAVNEDE:\n" + "\n".join(f"- {t}" for t in titles))
    if posts_by_cat["witness_appeal"]:
        titles = [p["title"] for p in posts_by_cat["witness_appeal"]]
        sections.append("VIDNEAPPELLER:\n" + "\n".join(f"- {t}" for t in titles))

    candidate_block, candidate_lookup = _candidate_sections(posts_by_cat)
    if candidate_block:
        sections.append(candidate_block)

    content_summary = "\n\n".join(sections)

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

    narrative, notable_raw = _parse_response(raw_content)
    if not narrative:
        raise RuntimeError("DeepSeek response did not include a usable narrative.")

    notable = []
    for item in notable_raw:
        if not isinstance(item, dict):
            continue
        post = candidate_lookup.get(item.get("id"))
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
    return {"narrative": narrative, "notable": notable}
