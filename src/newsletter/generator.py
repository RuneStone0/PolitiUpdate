"""Turn a region's posts into the briefing sent to that region's subscribers.

Deliberately LLM-free: produces a deterministic Danish briefing (subject + HTML
for the Brevo campaign + a plain-text twin for logs/previews).

Shape of a briefing (reworked 2026-09-26 after reviewing the copy that was
actually delivered — campaign 6, week 38):

* It **leads with the week's most read stories**. Reach comes from public X view
  counts (``src/common/x_reach.py``), so the highlight block is what people
  actually opened, not what a keyword filter guessed. One entry per headline.
* It is **short**: 5 highlights plus a one-line index capped by
  ``config.NEWSLETTER_INDEX_LIMIT``, instead of listing all 136 updates. The
  full week stays one link away on the owned archive page.
* It **always carries an owned link** (the week's ``politiupdates.dk`` archive,
  which is where the signup form lives). The delivered campaign 6 had 136 hrefs
  and every single one was x.com — a subscriber could not reach the site at all.

Counts (subject, intro, "… og N flere") always state the week's real number of
updates; only the *listing* is condensed.
"""

import html as _html

from src.bot.formatter import _district_prefix as district_short_name
from src.common import regions as region_map

from . import config

X_TWEET_URL = "https://x.com/PolitiUpdate/status/{id}"


def archive_url(week: int, year: int) -> str:
    """The published archive page for that week on the owned site.

    Unpadded week, matching ``src.digest.publisher``'s paths
    (``website/uge/{year}/{week}/``), so the link always resolves to the page
    the digest app committed.
    """
    return f"{config.SITE_BASE_URL.rstrip('/')}/uge/{year}/{week}/"


def visible_key(post: dict) -> tuple[str, str, str]:
    """What the reader actually sees for one entry: district + title + first line."""
    district = district_short_name(post.get("district") or "") or ""
    title = " ".join((post.get("title") or "").split()).casefold()
    snippet = " ".join(_first_line(post.get("body", "")).split()).casefold()
    return (district.casefold(), title, snippet)


def dedupe_visible(posts: list[dict]) -> list[dict]:
    """Keep the first entry per *visible* item (district + title + first line).

    The Ritzau feed re-announces one press-release page under a new id on every
    police update, so a story the police update N times is posted N times with
    the same headline. On X each post stands alone (a fresh ``ophævet`` update
    must be shareable), but inside a briefing the reader would see the same
    block twice — measured 2026-09-26 **on the copy that was actually
    delivered** (campaign 6): 136 list items of which 3 repeat an earlier item
    verbatim (in the DB, 5 of week 38's 136 posted rows are byte-identical
    repeats of an earlier row).

    The key is what the reader SEES, never the title alone: 42 of week 38's 136
    rows share a headline with a *different* body — genuine follow-ups such as
    "Metro-trafikken på Cityringen midlertidigt indstillet" followed by "vi er
    nu færdige med vores undersøgelser", which is the useful half. Counts
    (subject/heading) stay the week's real number of updates.
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for post in posts:
        key = visible_key(post)
        if key in seen:
            continue
        seen.add(key)
        out.append(post)
    return out


def title_key(post: dict) -> str:
    """Normalised headline — the identity key of a *story* inside a listing."""
    return " ".join((post.get("title") or "").split()).casefold()


def display_title(title: str) -> str:
    """Headlines are mirrored verbatim — including a police notice's ALL CAPS.

    An earlier revision sentence-cased all-caps headlines for display
    ("FODBOLDKAMP I BRØNDBY" -> "Fodboldkamp i Brøndby") and it could not be made
    safe: casing proper nouns back requires knowing which tokens are names, and
    the first attempt produced "i brøndby" — a mangled place name in the one
    line we want the reader to click. The project mirrors the police's own
    wording, so the headline stays exactly as published; the subject line
    carries a normal-case lead-in instead ("Ugens mest læste: …"), which keeps
    the shout out of the front of the inbox line.
    """
    return title


def summary(body: str, limit: int) -> str:
    """First line of the body, cut on a word boundary (never mid-word)."""
    text = " ".join(_first_line(body).split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-–")
    return f"{cut} …"


def index_entries(posts: list[dict]) -> list[dict]:
    """One entry per *story* (normalised headline), in posting order.

    ``posts`` arrive oldest-first, so the surviving entry keeps the first
    occurrence's position while its link follows the story's newest post — a
    reader who taps "Metro-trafikken … indstillet" reaches the update that says
    the metro runs again. ``updates`` records how many posted updates the story
    had, so nothing is silently lost.
    """
    entries: list[dict] = []
    by_key: dict[str, dict] = {}
    for post in posts:
        key = title_key(post)
        entry = by_key.get(key)
        if entry is None:
            by_key[key] = {"post": post, "link_post": post, "updates": 1}
            entries.append(by_key[key])
        else:
            entry["updates"] += 1
            entry["link_post"] = post
    return entries


def rank_highlights(posts: list[dict], views: dict[str, int] | None, limit: int) -> list[dict]:
    """The ``limit`` most read *stories*, best first — one entry per headline.

    Ranking is by total views. Measured on week 38 this matters: the raw top 5
    was one story five times over ("FODBOLDKAMP I BRØNDBY" ×5, the same
    press-release page re-announced). Collapsing by headline turns that into
    five different stories, which is what "highlight the interesting ones"
    actually means.
    """
    if not views or limit <= 0:
        return []

    best: dict[str, dict] = {}
    for post in posts:
        post_id = str(post.get("x_post_id") or "")
        count = views.get(post_id)
        if count is None:
            continue
        key = title_key(post)
        current = best.get(key)
        if current is None or count > current["views"]:
            best[key] = {"post": post, "views": count}

    ranked = sorted(
        best.values(),
        key=lambda entry: (-entry["views"], entry["post"].get("posted_at") or "", title_key(entry["post"])),
    )
    return ranked[:limit]


def generate(
    region_label: str,
    posts: list[dict],
    week: int,
    year: int,
    views: dict[str, int] | None = None,
) -> dict:
    """Return a newsletter dict: {region, subject, text, html, highlights, …}.

    ``views`` maps X post id -> view count (see ``src/common/x_reach``). Without
    it the briefing is the index-only variant (no highlight block, a neutral
    subject) — reach is decoration, never a reason to skip a send.
    """
    if not posts:
        return {
            "region": region_label,
            "subject": _subject(region_label, week, year, 0),
            "text": "",
            "html": "",
            "highlights": [],
            "listed": 0,
        }

    listed = dedupe_visible(posts)
    highlights = rank_highlights(listed, views, config.NEWSLETTER_HIGHLIGHTS)
    highlight_keys = {title_key(item["post"]) for item in highlights}

    entries = index_entries(listed)
    rest = [entry for entry in entries if title_key(entry["post"]) not in highlight_keys]
    shown = rest[: config.NEWSLETTER_INDEX_LIMIT]
    more = len(rest) - len(shown)

    count = len(posts)
    top_title = highlights[0]["post"].get("title") if highlights else None
    context = {
        "region": region_label,
        "week": week,
        "year": year,
        "count": count,
        "highlights": highlights,
        "shown": shown,
        "more": more,
        "summary_chars": config.NEWSLETTER_SUMMARY_CHARS,
    }

    return {
        "region": region_label,
        "subject": _subject(region_label, week, year, count, top_title),
        "text": _to_text(context),
        "html": _to_html(context),
        "highlights": [
            {
                "title": item["post"].get("title", ""),
                "district": district_short_name(item["post"].get("district") or "") or "",
                "views": item["views"],
                "url": _tweet_url(item["post"]),
            }
            for item in highlights
        ],
        "listed": len(shown) + len(highlights),
        "stories": len(entries),
    }


def _subject(region_label: str, week: int, year: int, count: int, top_title: str | None = None) -> str:
    """Subject line: name the week's most read story, brand in the sender field.

    Hook-first because a mail client shows ~40 characters on a phone, and the
    old "… (136 opdateringer)" put a number where the reason to open should be.
    The count still appears — in the preheader and in the briefing body.
    """
    if top_title:
        return f"Ugens mest læste: {_clip(display_title(top_title), 45)}"
    return f"PolitiUpdate · {region_label} · uge {week}, {year} ({count} opdateringer)"


def _heading(region_label: str, week: int, year: int, include_week: bool = True) -> str:
    """Human heading for one briefing.

    The country-wide briefing serves subscribers who have not picked a region,
    so "for Hele landet" would read like a region name — phrase it plainly.
    """
    if region_label == region_map.REGION_NATIONAL:
        base = "PolitiUpdate — ugens overblik fra hele landet"
    else:
        base = f"PolitiUpdate — ugens overblik for {region_label}"
    return f"{base} (uge {week}, {year})" if include_week else base


def _region_phrase(region_label: str) -> str:
    """Where the week's releases came from, for the intro line ("… politiet i X")."""
    if region_label == region_map.REGION_NATIONAL:
        return "i hele landet"
    return f"i {region_label}"


def _tweet_url(post: dict) -> str:
    post_id = post.get("x_post_id")
    return X_TWEET_URL.format(id=post_id) if post_id else ""


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-–") + " …"


# --- plain text (logs, console preview) -------------------------------------


def _to_text(context: dict) -> str:
    region = context["region"]
    week, year, count = context["week"], context["year"], context["count"]
    highlights, shown, more = context["highlights"], context["shown"], context["more"]

    lines = [_heading(region, week, year), "", f"{count} opdateringer fra politiet {_region_phrase(region)} i uge {week}."]
    if highlights:
        lines.append(f"Her er de {len(highlights)} sager, flest har læst — og hele ugens overblik.")
    else:
        lines.append("Her er ugens sager — og hele ugens overblik.")
    lines.append("")

    if highlights:
        lines.append("UGENS MEST LÆSTE SAGER")
        for number, item in enumerate(highlights, start=1):
            post = item["post"]
            district = district_short_name(post.get("district") or "") or ""
            lines.append(f"{number}. {display_title(post.get('title', ''))}"
                         + (f" — {district}" if district else ""))
            snippet = summary(post.get("body", ""), context["summary_chars"])
            if snippet:
                lines.append(f"   {snippet}")
            url = _tweet_url(post)
            if url:
                lines.append(f"   {url}")
            lines.append("")

    if shown:
        lines.append("FLERE SAGER FRA UGEN")
        for entry in shown:
            post = entry["link_post"]
            district = district_short_name(post.get("district") or "") or ""
            label = f"{district}: " if district else ""
            url = _tweet_url(post)
            lines.append(f"- {label}{display_title(post.get('title', ''))}"
                         + (f"  {url}" if url else ""))
        lines.append("")

    lines.append(f"Se hele ugens overblik: {archive_url(week, year)}")
    if more > 0:
        lines.append(f"({more} flere sager fra ugen er med på siden.)")
    return "\n".join(lines).strip()


# --- HTML (Brevo campaigns require htmlContent) -----------------------------

_FONT = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _to_html(context: dict) -> str:
    region = context["region"]
    week, year, count = context["week"], context["year"], context["count"]
    highlights, shown, more = context["highlights"], context["shown"], context["more"]
    site = _html.escape(archive_url(week, year), quote=True)
    phrase = _region_phrase(region)

    preheader = f"{count} opdateringer fra politiet {phrase} i uge {week}"
    preheader += (f" — de {len(highlights)} mest læste sager og hele ugens overblik."
                  if highlights else " — hele ugens overblik.")
    intro = f"{count} opdateringer fra politiet {phrase} i uge {week}."
    lead = (f"Her er de {len(highlights)} sager, flest har læst — og hele ugens overblik."
            if highlights else "Her er ugens sager — og hele ugens overblik.")

    parts: list[str] = []
    parts.append(
        '<!doctype html><html lang="da"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_html.escape(_heading(region, week, year))}</title></head>"
        '<body style="margin:0;padding:0;background:#f4f5f7;-webkit-text-size-adjust:100%">'
        # Preheader: the line most inboxes show next to the subject.
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#f4f5f7;'
        f'font-size:1px;line-height:1px">{_html.escape(preheader)}</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background:#f4f5f7"><tr><td align="center" style="padding:18px 10px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;max-width:600px;background:#ffffff;border-radius:14px;border-collapse:separate;font-family:{_FONT}">'
    )

    # Header band — brand + which week/region this is.
    parts.append(
        '<tr><td style="background:#0f172a;padding:20px 24px;border-radius:14px 14px 0 0">'
        f'<a href="{site}" style="color:#ffffff;text-decoration:none;font-size:20px;'
        'font-weight:700;letter-spacing:.2px">PolitiUpdate</a>'
        f'<div style="color:#94a3b8;font-size:13px;margin-top:6px">Uge {week}, {year} · '
        f'{_html.escape(region)}</div></td></tr>'
    )

    # Intro.
    parts.append(
        '<tr><td style="padding:22px 24px 6px">'
        f'<h1 style="margin:0 0 8px;font-size:20px;line-height:1.3;color:#0f172a;font-weight:700">'
        f'{"Ugens mest læste sager" if highlights else _html.escape(_heading(region, week, year, include_week=False))}</h1>'
        f'<p style="margin:0;color:#475569;font-size:14px;line-height:1.6">{_html.escape(intro)}'
        f'<br>{_html.escape(lead)}</p></td></tr>'
    )

    # Highlight block, in rank order.
    for number, item in enumerate(highlights, start=1):
        post = item["post"]
        url = _tweet_url(post)
        href = _html.escape(url, quote=True) if url else site
        district = district_short_name(post.get("district") or "") or ""
        snippet = summary(post.get("body", ""), context["summary_chars"])
        body = [
            '<tr><td style="padding:14px 24px 0">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            '<td width="28" valign="top" style="font-size:16px;font-weight:700;color:#cbd5e1;'
            f'padding:1px 6px 0 0">{number}</td><td valign="top">'
            f'<a href="{href}" style="color:#0f172a;font-size:16px;font-weight:700;'
            f'text-decoration:none;line-height:1.4">{_html.escape(display_title(post.get("title", "")))}</a>'
        ]
        if district:
            body.append(
                f'<div style="color:#64748b;font-size:11px;letter-spacing:.5px;'
                f'text-transform:uppercase;margin:5px 0 6px">{_html.escape(district)}</div>'
            )
        if snippet:
            body.append(
                f'<div style="color:#334155;font-size:14px;line-height:1.6">{_html.escape(snippet)}</div>'
            )
        body.append("</td></tr></table></td></tr>")
        if number < len(highlights):
            body.append(
                '<tr><td style="padding:0 24px"><div style="border-top:1px solid #e8ecf1;'
                'margin-top:14px"></div></td></tr>'
            )
        parts.append("".join(body))

    # Primary call to action — the owned page (and its signup form).
    parts.append(
        '<tr><td style="padding:20px 24px 4px">'
        f'<a href="{site}" style="display:inline-block;background:#0f172a;color:#ffffff;'
        'padding:13px 22px;border-radius:9px;text-decoration:none;font-weight:600;font-size:15px">'
        f'Se alle {count} opdateringer →</a></td></tr>'
    )

    # The rest of the week as a scannable index, one line per story.
    if shown:
        rows = []
        for entry in shown:
            post = entry["link_post"]
            url = _tweet_url(post)
            href = _html.escape(url, quote=True) if url else site
            district = district_short_name(post.get("district") or "") or ""
            label = (
                f'<strong style="color:#0f172a">{_html.escape(district)}:</strong> ' if district else ""
            )
            rows.append(
                '<tr><td style="padding:0 0 9px">'
                f'<a href="{href}" style="color:#334155;font-size:14px;line-height:1.5;'
                f'text-decoration:none">{label}{_html.escape(display_title(post.get("title", "")))}</a>'
                "</td></tr>"
            )
        more_line = ""
        if more > 0:
            more_line = (
                f'<p style="margin:8px 0 0;color:#64748b;font-size:13px">… og {more} flere sager i '
                f'<a href="{site}" style="color:#1d4ed8;text-decoration:none">hele ugens overblik</a>.</p>'
            )
        parts.append(
            '<tr><td style="padding:26px 24px 6px">'
            '<div style="border-top:1px solid #e8ecf1;padding-top:18px">'
            '<h2 style="margin:0 0 12px;font-size:15px;color:#0f172a;font-weight:700">'
            "Flere sager fra ugen</h2>"
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            + "".join(rows)
            + "</table>" + more_line + "</div></td></tr>"
        )

    # Footer — why this arrived, and what the project is.
    parts.append(
        '<tr><td style="background:#f8fafc;border-top:1px solid #e8ecf1;padding:20px 24px;'
        'border-radius:0 0 14px 14px">'
        '<p style="margin:0;color:#64748b;font-size:12px;line-height:1.7">'
        f'Du modtager dette nyhedsbrev, fordi du har tilmeldt dig på '
        f'<a href="{site}" style="color:#64748b">politiupdates.dk</a>.<br>'
        "PolitiUpdate er et uofficielt, automatisk spejl af politiets pressemeddelelser. "
        "Ingen tilknytning til politiet.<br>"
        "Afmelding: brug linket nederst i denne e-mail.</p></td></tr>"
        "</table></td></tr></table></body></html>"
    )
    return "".join(parts)


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
