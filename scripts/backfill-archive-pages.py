#!/usr/bin/env python3
"""Re-render published digest archive pages from their own digest.json.

The weekly archive pages under ``website/uge/{year}/{week}/`` are *generated*
artifacts: ``src/digest/publisher.py`` commits them straight to ``main``, so a
change to the template only reaches weeks published *after* that change. This
script applies the current template to weeks that are already live by
re-rendering each page from the ``digest.json`` the digest app published for it.

The digest data is fetched from the **live site** (not from the local tree) on
purpose: the local checkout is routinely behind ``main``, and only the published
``digest.json`` carries the forward-pager link the digest app writes to the
previous week after publishing a new one. Re-rendering from it is therefore
exactly what the digest app itself would write — no hand-editing of generated
files, which is what would silently revert those pager links.

It also refreshes ``website/sitemap.xml`` so every published week stays listed:
the sitemap was hand-maintained and lagged the site (week 37 was live for four
days without ever appearing in it), and since discovery here *reads* the
sitemap, a stale list hides the very week that needs re-rendering. Weeks past the
newest listed one are therefore probed for directly.

Writes nothing to git: run it, review ``git diff``, then commit/push (which is
what deploys the site).

Usage:
    python scripts/backfill-archive-pages.py 33 34 35 36 37
    python scripts/backfill-archive-pages.py --year 2026 --all
    python scripts/backfill-archive-pages.py 37 --check   # report, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.digest import publisher  # noqa: E402  (path set up above)

WEBSITE = REPO_ROOT / "website"

_DIGEST_CACHE: dict[tuple[int, int], dict | None] = {}


def live_weeks(year: int) -> list[int]:
    """Discover published weeks from the live sitemap (authoritative — the local
    tree can be behind)."""
    url = f"{publisher.SITE_BASE_URL}/sitemap.xml"
    with urlopen(url, timeout=30) as resp:  # noqa: S310 (fixed https URL)
        sitemap = resp.read().decode("utf-8")
    weeks = set()
    for part in sitemap.split(f"/uge/{year}/")[1:]:
        head = part.split("/", 1)[0]
        if head.isdigit():
            weeks.add(int(head))
    return sorted(weeks)


def live_weeks_complete(year: int) -> list[int]:
    """Every published week of ``year``: the live sitemap **plus** the weeks it
    does not list (yet).

    The sitemap is written by the digest run (``publisher.update_sitemap``), but
    it was hand-maintained before that and lagged the pages — week 37 was live
    for four days without appearing in it. Since discovery reads the sitemap, a
    stale list silently hides exactly the week that needs re-rendering, so probe
    forward past the newest listed week as well.
    """
    weeks = set(live_weeks(year))
    newest = max(weeks, default=0)
    today = datetime.now(timezone.utc).isocalendar()
    probe_until = today.week if today.year == year else newest
    for week in range(newest + 1, probe_until + 1):
        if fetch_digest(year, week, quiet=True) is not None:
            weeks.add(week)
    return sorted(weeks)


def fetch_digest(year: int, week: int, quiet: bool = False) -> dict | None:
    key = (year, week)
    if key in _DIGEST_CACHE:
        return _DIGEST_CACHE[key]
    url = f"{publisher.SITE_BASE_URL}/uge/{year}/{week}/digest.json"
    digest: dict | None
    try:
        with urlopen(url, timeout=30) as resp:  # noqa: S310 (fixed https URL)
            digest = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        if not quiet:  # probing a week that is simply not published yet is normal
            print(f"  ! uge {week}: could not fetch {url} ({exc})")
        digest = None
    _DIGEST_CACHE[key] = digest
    return digest


def refresh_sitemap(year: int, weeks: list[int], check: bool) -> bool:
    """Make the local ``website/sitemap.xml`` list every published week.

    Mirrors what ``publisher.update_sitemap`` now does on every digest run, for
    weeks that were published before the sitemap was maintained automatically
    (the live file listed weeks 33–36 while 37 was already published).
    """
    target = WEBSITE / "sitemap.xml"
    existing = target.read_text(encoding="utf-8") if target.is_file() else None
    if existing is None:
        entries: dict[tuple[int, int], str] = {}
        head_blocks: list[str] | None = None
    else:
        entries, head_blocks = publisher.parse_sitemap(existing)
        head_blocks = head_blocks or None
    for week in weeks:
        digest = fetch_digest(year, week)
        if digest is not None and not entries.get((year, week)):
            entries[(year, week)] = publisher.iso_week_lastmod(digest)
    content = publisher.render_sitemap(entries, head_blocks)

    if existing == content:
        print(f"  = sitemap: already lists {_weeks_label(year, sorted(entries))}")
        return True
    if check:
        print(f"  * sitemap: would be updated to list {_weeks_label(year, sorted(entries))}")
        return True
    target.write_text(content, encoding="utf-8")
    print(f"  updated: website/sitemap.xml ({_weeks_label(year, sorted(entries))})")
    return True


def _weeks_label(year: int, weeks: list[tuple[int, int]]) -> str:
    return ", ".join(f"uge {w}/{y}" for y, w in weeks if y == year) or "no weeks"


def render_week(year: int, week: int, check: bool) -> bool:
    digest = fetch_digest(year, week)
    if digest is None:
        return False

    html_text = publisher._render_archive_html(digest)
    target = WEBSITE / "uge" / str(year) / str(week) / "index.html"

    if "digest-signup" not in html_text:
        print(f"  ! uge {week}: rendered page has no signup block — template broken?")
        return False

    if check:
        if target.is_file() and target.read_text(encoding="utf-8") == html_text:
            print(f"  = uge {week}: already up to date")
        elif target.is_file():
            print(f"  * uge {week}: would be re-rendered (changes)")
        else:
            print(f"  + uge {week}: would be created")
        return True

    existed = target.is_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html_text, encoding="utf-8")
    verb = "re-rendered" if existed else "created"
    print(f"  {verb}: website/uge/{year}/{week}/index.html "
          f"({digest.get('total_posts', '?')} items, {len(html_text)} bytes)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("weeks", nargs="*", type=int, help="ISO week numbers")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--all", action="store_true", help="every published week of --year")
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    weeks = args.weeks
    if args.all:
        weeks = sorted(set(weeks) | set(live_weeks_complete(args.year)))
    if not weeks:
        parser.error("give week numbers, or --all to use the live sitemap")

    ok = 0
    for week in weeks:
        if render_week(args.year, week, args.check):
            ok += 1

    # The sitemap is how search engines (and this script) find the archive, so a
    # refreshed page that is missing from it is only half published.
    refresh_sitemap(args.year, weeks, args.check)

    print(f"{ok}/{len(weeks)} week page(s) handled for {args.year}"
          + (" (dry run)" if args.check else ""))
    return 0 if ok == len(weeks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
