"""Generate a Danish weekly digest narrative via DeepSeek."""

import logging

import requests

from . import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Du er redaktør for PolitiUpdate, et dansk nyhedsbrev der opsummerer ugens "
    "politimeddelelser. Du skriver præcise, faktabaserede resuméer på dansk. "
    "Skriv i en neutral, journalistisk tone.\n\n"
    "REGLER:\n"
    "- Bevar navne, aldre og steder i efterlysningssager — de er vigtige for læseren.\n"
    "- Undgå at specificere anholdelses- og sigtelsessager med navne.\n"
    "- Skriv KUN det faktiske resumé. Ingen introduktion, ingen overskrift, ingen kommentarer.\n"
    "- Brug korrekt dansk grammatik og tegnsætning.\n"
    "- Undgå gentagelser og fyldord."
)


def generate(data: dict) -> str:
    """Generate a narrative digest for the given week data.

    Returns the narrative string. Raises RuntimeError if the LLM call fails.
    """
    if not config.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is not set — cannot generate digest narrative.")

    week = data["week"]
    year = data["year"]
    total = data["total_posts"]
    cats = data["categories"]
    posts_by_cat = data["posts_by_category"]

    # Build a compact representation of the posts for the prompt
    sections = []
    if posts_by_cat["missing_person"]:
        titles = [p["title"] for p in posts_by_cat["missing_person"]]
        sections.append("EFTERLYSNINGER/SAVNEDE:\n" + "\n".join(f"- {t}" for t in titles))
    if posts_by_cat["witness_appeal"]:
        titles = [p["title"] for p in posts_by_cat["witness_appeal"]]
        sections.append("VIDNEAPPELLER:\n" + "\n".join(f"- {t}" for t in titles))
    if posts_by_cat["arrest"]:
        count = cats["arrest"]
        sections.append(f"ANHOLDELSER/SIGTELSER: {count} sager")
    if posts_by_cat["other"]:
        count = cats["other"]
        sections.append(f"ØVRIGE SAGER: {count} meddelelser")

    content_summary = "\n\n".join(sections)

    user_prompt = (
        f"Skriv et ugeoverblik for uge {week}, {year}. "
        f"Politiet udsendte {total} meddelelser i alt.\n\n"
        f"Fordeling:\n{content_summary}\n\n"
        "Skriv et kort resumé på 3-5 sætninger der fremhæver ugens vigtigste sager. "
        "Nævn konkrete efterlysningssager ved navn hvis relevant. "
        "Afslut med det samlede antal meddelelser."
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
                "max_tokens": 400,
            },
            timeout=config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"DeepSeek API request failed: {e}") from e

    try:
        narrative = resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Failed to parse DeepSeek response: {e}") from e

    logger.info("Generated digest narrative (%d chars)", len(narrative))
    return narrative
