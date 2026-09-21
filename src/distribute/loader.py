"""Load published weekly digests from the repo's committed archive pages.

The digest app commits ``website/uge/{year}/{week}/digest.json`` +
``index.html`` via the GitHub Contents API on every weekly run, so the
published archive *is* the source of truth for what actually went out. The
channel kit is therefore generated from published data instead of re-querying
the bot DB — no second code path that can disagree with what readers saw.
"""

import json
import re
from pathlib import Path

_WEEK_RE = re.compile(r"^(\d{4})$")


class DigestNotFoundError(FileNotFoundError):
    """Raised when no published digest exists for the requested week."""


def _week_dirs(root: Path):
    """Yield ``(year, week, path)`` for every published archive under *root*."""
    for year_dir in sorted(root.iterdir() if root.is_dir() else []):
        if not year_dir.is_dir() or not _WEEK_RE.match(year_dir.name):
            continue
        for week_dir in sorted(year_dir.iterdir()):
            if not week_dir.is_dir() or not week_dir.name.isdigit():
                continue
            meta = week_dir / "digest.json"
            if meta.is_file():
                yield int(year_dir.name), int(week_dir.name), meta


def available_weeks(root: str | Path) -> list[tuple[int, int]]:
    """Return every published ``(year, week)`` under *root*, oldest first."""
    return [(y, w) for y, w, _ in _week_dirs(Path(root))]


def latest_week(root: str | Path) -> tuple[int, int]:
    """Return the most recently published ``(year, week)`` under *root*."""
    weeks = available_weeks(root)
    if not weeks:
        raise DigestNotFoundError(f"no published digests found under {root}")
    return weeks[-1]


def load_digest(root: str | Path, year: int, week: int) -> dict:
    """Load and validate one published digest.

    Raises :class:`DigestNotFoundError` when the week was never published
    (e.g. the local checkout is behind ``main`` — run ``git fetch`` first).
    """
    path = Path(root) / str(year) / str(week) / "digest.json"
    if not path.is_file():
        raise DigestNotFoundError(
            f"no published digest at {path} — is the checkout up to date "
            f"(git fetch/pull) and is that week (year={year}, week={week}) published?"
        )
    with path.open(encoding="utf-8") as fh:
        digest = json.load(fh)
    missing = [k for k in ("week", "year", "total_posts") if k not in digest]
    if missing:
        raise ValueError(f"{path} is not a digest.json (missing keys: {missing})")
    digest.setdefault("categories", {})
    digest.setdefault("notable", [])
    digest.setdefault("region_items", {})
    return digest


def week_label(year: int, week: int) -> str:
    """Human (Danish) label for the reporting window, e.g. ``uge 37/2026``."""
    return f"uge {week}/{year}"


def archive_url(site_base: str, year: int, week: int) -> str:
    """Public URL of the week's published archive page (no tracking params)."""
    return f"{site_base.rstrip('/')}/uge/{year}/{week}/"
