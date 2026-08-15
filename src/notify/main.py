"""Notification CLI entrypoint.

Run with:
    python -m src.notify daily    # health check across services
    python -m src.notify weekly   # X follower-count summary
"""

import argparse
import logging
import sys

from . import followers, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Send PolitiUpdate notifications via Prowl.")
    parser.add_argument("mode", choices=["daily", "weekly"], help="Which check to run.")
    args = parser.parse_args(argv)

    try:
        if args.mode == "daily":
            health.run()
        else:
            followers.run()
    except Exception:
        logger.exception("Notification job failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
