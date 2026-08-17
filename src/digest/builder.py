"""Query the database and group this week's posts by category."""

import sqlite3
from datetime import datetime, timedelta, timezone

from . import config

# Reuse keyword lists from formatter, plus additional patterns for categorization
MISSING_PERSON_KEYWORDS = [
    "efterlysning", "savnet", "eftersøgning",
]
WITNESS_APPEAL_KEYWORDS = [
    "vidneappel", "har du set", "har du oplysninger", "bedes du kontakte",
    "kontakt politiet", "vidner søges",
]
ARREST_KEYWORDS = [
    "anholdt", "anholdte", "fængslet", "varetægtsfængslet", "sigtet",
]


def _categorize(title: str, body: str) -> str:
    text = (title + " " + body).lower()
    if any(kw in text for kw in MISSING_PERSON_KEYWORDS):
        return "missing_person"
    if any(kw in text for kw in WITNESS_APPEAL_KEYWORDS):
        return "witness_appeal"
    if any(kw in text for kw in ARREST_KEYWORDS):
        return "arrest"
    return "other"


def build(year: int, week: int) -> dict:
    """Return a digest data dict for the given ISO year+week.

    The "week" spans Monday 00:00 to Sunday 23:59 UTC.
    """
    monday = _iso_week_start(year, week)
    sunday_end = monday + timedelta(days=7)

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute(
        """
        SELECT title, body, posted_at, x_post_id
        FROM posts
        WHERE status = 'posted'
          AND posted_at >= ?
          AND posted_at < ?
        ORDER BY posted_at
        """,
        (monday.isoformat(), sunday_end.isoformat()),
    ).fetchall()
    conn.close()

    categories: dict[str, list[dict]] = {
        "missing_person": [],
        "witness_appeal": [],
        "arrest": [],
        "other": [],
    }
    for title, body, posted_at, x_post_id in rows:
        cat = _categorize(title, body)
        categories[cat].append(
            {"title": title, "body": body, "posted_at": posted_at, "x_post_id": x_post_id}
        )

    return {
        "week": week,
        "year": year,
        "total_posts": len(rows),
        "categories": {k: len(v) for k, v in categories.items()},
        "posts_by_category": categories,
    }


def _iso_week_start(year: int, week: int) -> datetime:
    """Return UTC midnight of the Monday starting ISO week `week` of `year`."""
    jan4 = datetime(year, 1, 4, tzinfo=timezone.utc)
    week_one_monday = jan4 - timedelta(days=jan4.weekday())
    return week_one_monday + timedelta(weeks=week - 1)


def current_week() -> tuple[int, int]:
    """Return (year, week) for the ISO week that just ended (last Sunday)."""
    today = datetime.now(timezone.utc).date()
    # Use the previous week so we have a complete dataset
    last_sunday = today - timedelta(days=today.weekday() + 1)
    iso = last_sunday.isocalendar()
    return iso.year, iso.week
