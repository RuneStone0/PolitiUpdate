"""Notification CLI entrypoint.

Run with:
    python -m src.notify           # persistent loop: self-schedules the
                                    # daily health check and weekly stats +
                                    # follower check (see loop.py)
    python -m src.notify daily     # run the daily health check once and exit
    python -m src.notify weekly    # run the weekly check once and exit
"""

import argparse
import logging
import sys

from . import health, loop, weekly

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Send PolitiUpdate notifications via Prowl.")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["daily", "weekly"],
        default=None,
        help="Run a single check and exit. Omit to run the persistent scheduling loop.",
    )
    args = parser.parse_args(argv)

    try:
        if args.mode == "daily":
            health.run()
        elif args.mode == "weekly":
            weekly.run()
        else:
            loop.run()
    except Exception:
        logger.exception("Notification job failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
