"""Turn a region's posts into the briefing text sent to that region's subscribers.

Deliberately LLM-free for now: produces a clean, deterministic Danish plain-text
summary (subject + a short bullet per release). A later pass can swap this for a
DeepSeek narrative (mirroring ``src/digest/generator``) once we want prose — but
keeping it deterministic keeps ``--dry-run`` testable with no API key.
"""

from src.bot.formatter import _district_prefix as district_short_name

X_TWEET_URL = "https://x.com/PolitiUpdate/status/{id}"


def generate(region_label: str, posts: list[dict], week: int, year: int) -> dict:
    """Return a newsletter dict: {subject, text} for one region."""
    if not posts:
        return {"region": region_label, "subject": _subject(region_label, week, year, 0), "text": ""}

    heading = f"PolitiUpdate — ugens overblik for {region_label} (uge {week}, {year})"
    lines = [heading, ""]
    for post in posts:
        title = post.get("title", "")
        district = district_short_name(post.get("district") or "") or ""
        prefix = f"{district} | " if district else ""
        snippet = _first_line(post.get("body", ""))
        link = X_TWEET_URL.format(id=post.get("x_post_id")) if post.get("x_post_id") else ""
        lines.append(f"- {prefix}{title}")
        if snippet:
            lines.append(f"  {snippet}")
        if link:
            lines.append(f"  {link}")
        lines.append("")

    return {
        "region": region_label,
        "subject": _subject(region_label, week, year, len(posts)),
        "text": "\n".join(lines).strip(),
    }


def _subject(region_label: str, week: int, year: int, count: int) -> str:
    return f"PolitiUpdate · {region_label} · uge {week}, {year} ({count} opdateringer)"


def _first_line(body: str) -> str:
    """Return the first non-empty line of the body, trimmed."""
    if not body:
        return ""
    for paragraph in body.split("\n\n"):
        for line in paragraph.split("\n"):
            line = line.strip()
            if line:
                return line
    return ""
