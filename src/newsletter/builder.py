"""Query the DB and group this week's posted releases by region.

Mirrors ``src/digest/builder.py``: pulls the past ISO week's ``posted`` posts
from the shared DB, then buckets each by region using
``src.common.regions.district_to_region``. Nationwide releases
(``REGION_NATIONAL``) are returned separately and are *auto-included* into
every region's briefing (per the PLAN.md spec), so a Hovedstaden subscriber
still sees a Rigspolitiet-wide story.
"""

import sqlite3
from datetime import date, datetime, timedelta, timezone

from src.common import regions as region_map

from . import config

UNKNOWN_REGION = "Ukendt"


def build(year: int, week: int) -> dict:
    """Return a newsletter data dict for the given ISO year+week.

    The week spans Monday 00:00 to Sunday 23:59 UTC.
    """
    monday = _iso_week_start(year, week)
    sunday_end = monday + timedelta(days=7)

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute(
        """
        SELECT title, body, posted_at, x_post_id, district
        FROM posts
        WHERE status = 'posted'
          AND posted_at >= ?
          AND posted_at < ?
        ORDER BY posted_at
        """,
        (monday.isoformat(), sunday_end.isoformat()),
    ).fetchall()
    conn.close()

    # region -> list of posts belonging to it *only* (national kept separate)
    regional: dict[str, list[dict]] = {}
    national: list[dict] = []
    unknown: list[dict] = []
    all_posts: list[dict] = []

    for title, body, posted_at, x_post_id, district in rows:
        post = {
            "title": title,
            "body": body,
            "posted_at": posted_at,
            "x_post_id": x_post_id,
            "district": district,
        }
        reg = region_map.district_to_region(district)
        all_posts.append(post)
        if reg == region_map.REGION_NATIONAL:
            national.append(post)
        elif reg is None:
            unknown.append(post)
        else:
            regional.setdefault(reg, []).append(post)

    # Bucket each subscriber-facing region, auto-including national releases.
    regions_out: dict[str, list[dict]] = {}
    for reg in region_map.REGIONS:
        regions_out[reg] = regional.get(reg, []) + list(national)

    totals = {"regional": len(rows) - len(national), "national": len(national)}
    return {
        "week": week,
        "year": year,
        "total_posts": len(rows),
        "totals": totals,
        "regions": regions_out,
        "national": national,
        "unknown": unknown,
        # Every release of the week, in posting order — the country-wide
        # briefing. Subscribers without a region receive this one instead of
        # nothing (see ``src/newsletter/routing.py``).
        "everything": all_posts,
        "national_label": region_map.REGION_NATIONAL,
        "unknown_label": UNKNOWN_REGION,
    }


def _iso_week_start(year: int, week: int) -> datetime:
    """Return UTC midnight of the Monday starting ISO week `week` of `year`."""
    jan4 = datetime(year, 1, 4, tzinfo=timezone.utc)
    week_one_monday = jan4 - timedelta(days=jan4.weekday())
    return week_one_monday + timedelta(weeks=week - 1)


def current_week(today: date | None = None) -> tuple[int, int]:
    """Return (year, week) for the ISO week the newsletter should cover.

    Intended to run weekly like the digest: on any day it returns the most
    recently completed ISO week (ending last Sunday). The optional `today`
    makes the boundary deterministic under test.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()
    last_sunday = today - timedelta(days=today.weekday() + 1)
    iso = last_sunday.isocalendar()
    return iso.year, iso.week
