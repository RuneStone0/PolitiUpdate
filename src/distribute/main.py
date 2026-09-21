"""CLI: generate the week's paste-ready channel kit.

Usage::

    python -m src.distribute                      # latest published week
    python -m src.distribute --week 37            # a specific week
    python -m src.distribute --channel reddit --stdout
    python -m src.distribute --channel facebook --region Hovedstaden
    python -m src.distribute --list               # published weeks available

Writes ``<out>/<year>-W<week>-<channel>.md`` files plus a JSON summary.
Offline and read-only: it only reads the committed archive and writes drafts
under ``data/`` (gitignored) — it never posts and never commits.
"""

import argparse
import json
import sys
from pathlib import Path

from . import config, generator, loader

CHANNELS = ("reddit", "facebook", "x", "summary")


def _slug(text: str) -> str:
    return (
        text.lower()
        .replace("æ", "ae")
        .replace("ø", "oe")
        .replace("å", "aa")
        .replace("/", "-")
        .replace(" ", "-")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.distribute",
        description="Generate paste-ready channel drafts from a published weekly digest.",
    )
    parser.add_argument("--week", type=int, help="ISO week number (default: latest published)")
    parser.add_argument("--year", type=int, help="ISO year (default: year of --week/latest)")
    parser.add_argument(
        "--channel",
        action="append",
        choices=("all", *CHANNELS),
        help="channel(s) to generate (default: all)",
    )
    parser.add_argument(
        "--region",
        help="region for the Facebook draft (one of Hovedstaden/Sjælland/Jylland/Fyn; "
        "default: the region with most items)",
    )
    parser.add_argument("--published-dir", default=config.PUBLISHED_DIR,
                        help="root of published archives (default: website/uge)")
    parser.add_argument("--out", default=config.OUTPUT_DIR,
                        help="output directory for the drafts (default: data/distribution)")
    parser.add_argument("--site-base", default=config.SITE_BASE_URL,
                        help="public site base URL used in the drafts")
    parser.add_argument("--stdout", action="store_true", help="print drafts instead of writing files")
    parser.add_argument("--list", action="store_true", help="list published weeks and exit")
    return parser


def _resolve_week(published_dir: str, args: argparse.Namespace) -> tuple[int, int]:
    if args.week:
        year = args.year or loader.latest_week(published_dir)[0]
        return year, args.week
    latest = loader.latest_week(published_dir)
    return (args.year or latest[0], latest[1])


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        weeks = loader.available_weeks(args.published_dir)
        if not weeks:
            print(f"no published digests under {args.published_dir}", file=sys.stderr)
            return 1
        for year, week in weeks:
            print(f"{year}-W{week:02d}")
        return 0

    try:
        year, week = _resolve_week(args.published_dir, args)
        digest = loader.load_digest(args.published_dir, year, week)
    except loader.DigestNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    channels = args.channel or ["all"]
    if "all" in channels:
        channels = list(CHANNELS)

    region = args.region or generator.region_with_most_items(digest)
    if "facebook" in channels and not region:
        print("warning: no regional items published — skipping the Facebook draft",
              file=sys.stderr)
        channels = [c for c in channels if c != "facebook"]
    if "facebook" in channels and region not in generator.REGION_ORDER:
        print(f"error: unknown region {region!r}; pick one of {generator.REGION_ORDER}",
              file=sys.stderr)
        return 2

    drafts: dict[str, str] = {"reddit": generator.build_reddit_post(digest, args.site_base)}
    if "facebook" in channels and region:
        drafts["facebook"] = generator.build_facebook_post(digest, args.site_base, region)
    drafts["x"] = generator.build_x_post(digest, args.site_base)
    summary = generator.build_summary(digest, args.site_base)

    if args.stdout:
        for name in ("reddit", "facebook", "x"):
            if name in drafts:
                print(f"===== {name} ({region if name == 'facebook' else ''}) =====")
                print(drafts[name])
                print()
        print("===== summary =====")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{year}-W{week:02d}"
    written = []
    for name, text in drafts.items():
        path = out_dir / f"{stem}-{name}.md"
        path.write_text(text + "\n", encoding="utf-8")
        written.append(path)
    summary_path = out_dir / f"{stem}-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    written.append(summary_path)

    print(f"channel kit for {stem}: {digest['total_posts']} posts"
          + (f", facebook region = {region}" if region else ""))
    for path in written:
        print(f"  wrote {path}")
    print("Reminder: r/Denmark needs mod-permission first (rule 5) — "
          "see docs/growth/distribution-playbook.md §2.")
    return 0
