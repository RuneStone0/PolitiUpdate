"""LLM-based summarization via DeepSeek API (OpenAI-compatible)."""

import logging

import requests

from .config import LLM_API_KEY, LLM_MODEL, LLM_BASE_URL, LLM_TIMEOUT

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "Du er en præcis dansk redaktør for politiets kortmeddelelser (Politi Update). "
    "Din opgave er at forkorte en politi-opdatering, så den passer inden for et "
    "tegnbegrænsning, uden at miste nogen fakta.\n\n"
    "REGLER:\n"
    "- Bevar ALLE fakta: navne, aldre, steder, tidspunkter, signalementer, "
    "telefonnumre (114), gadenavne, byer, retssteder, sigtelser, kendelser.\n"
    "- Bevar datoer og klokkeslæt uændret.\n"
    "- Fjern fyldord og gentagelser, men tilføj ALDRIG nye oplysninger.\n"
    "- Hvis teksten indeholder en opfordring (fx 'kontakt politiet på 114'), "
    "skal den bevares.\n"
    "- Output KUN den forkortede tekst. Ingen introduktion, ingen kommentarer, "
    "ingen anførselstegn omkring resultatet.\n"
    "- Brug korrekt dansk grammatik og tegnsætning."
)


def summarize(text: str, max_chars: int) -> str | None:
    """Condense text to fit within max_chars using DeepSeek.

    Returns the condensed text, or None if the API call fails.
    """
    if not LLM_API_KEY:
        logger.warning("LLM_API_KEY not configured, cannot summarize")
        return None

    user_prompt = (
        f"Forkort følgende politi-opdatering til højst {max_chars} tegn "
        f"(inklusive mellemrum og tegnsætning):\n\n{text}"
    )

    try:
        resp = requests.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 600,
            },
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        # Not alert-worthy on its own — formatter._condense_or_truncate()
        # falls back to plain truncation whenever this returns None, so a
        # DeepSeek hiccup degrades tweet quality (LLM-condensed vs.
        # truncated) but never loses a post. Same self-healing bucket as
        # the X API failure paths in poster.py.
        logger.warning("DeepSeek API request failed: %s", e)
        return None

    try:
        data = resp.json()
        result = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as e:
        logger.warning("Failed to parse DeepSeek response: %s", e)
        return None

    logger.debug(
        "Summarized %d → %d chars", len(text), len(result),
    )
    return result
