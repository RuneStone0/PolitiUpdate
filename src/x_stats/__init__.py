"""X stats app — fetches X account metrics and caches them for the static website.

Runs as its own container service (see the `x-stats` entry in docker-compose.yml).
"""

from .main import fetch_stats

__all__ = ["fetch_stats"]
