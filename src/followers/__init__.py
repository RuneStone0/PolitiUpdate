"""Follower sync app — follows back new followers, unfollows users who unfollowed us.

Standalone app, separate from the posting bot. Intended to run periodically
(see the `followers` entry in docker-compose.yml) rather than continuously,
since X API v2 follow/followers endpoints are tightly rate-limited.
"""

from .main import sync

__all__ = ["sync"]
