"""Turn a region's posts into the briefing sent to that region's subscribers.

Deliberately LLM-free for now: produces a clean, deterministic Danish briefing
(subject + a short block per release) in both plain text (for logging / the
console preview) and HTML (Brevo campaigns require ``htmlContent`` — there is
no plain-text-only campaign). A later pass can swap this for a DeepSeek
narrative (mirroring ``src/digest/generator``) once we want prose — keeping it
deterministic keeps ``--dry-run`` testable with no API key.
"""

import html as _html

from src.bot.formatter import _district_prefix as district_short_name

X_TWEET_URL = "https://x.com/PolitiUpdate/status/{id}"


def generate(region_label: str, posts: list[dict], week: int, year: int) -> dict:
    """Return a newsletter dict: {region, subject, text, html} for one region."""
    if not posts:
        return {
            "region": region_label,
            "subject": _subject(region_label, week, year, 0),
            "text": "",
            "html": "",
        }

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
        "html": _to_html(region_label, posts, week, year),
    }


def _subject(region_label: str, week: int, year: int, count: int) -> str:
    return f"PolitiUpdate · {region_label} · uge {week}, {year} ({count} opdateringer)"


def _to_html(region_label: str, posts: list[dict], week: int, year: int) -> str:
    """Render the briefing as simple, inbox-safe HTML (for the Brevo campaign)."""
    items = []
    for post in posts:
        title = _html.escape(post.get("title", ""))
        district = district_short_name(post.get("district") or "") or ""
        prefix = f"{_html.escape(district)} | " if district else ""
        snippet = _html.escape(_first_line(post.get("body", "")))
        link = X_TWEET_URL.format(id=post.get("x_post_id")) if post.get("x_post_id") else ""
        item = [f"<li><strong>{prefix}{title}</strong>"]
        if snippet:
            item.append(f"<br>{snippet}")
        if link:
            item.append(f'<br><a href="{link}">Se opslaget på X</a>')
        item.append("</li>")
        items.append("".join(item))

    heading = _html.escape(f"PolitiUpdate — ugens overblik for {region_label}")
    return (
        '<div style="font-family:Helvetica,Arial,sans-serif;color:#1f2937;line-height:1.5">'
        f"<h2>{heading}</h2>"
        f"<p>Uge {week}, {year}</p>"
        "<ul>" + "".join(items) + "</ul>"
        "</div>"
    )


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
