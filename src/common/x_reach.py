"""Public X view counts for our own posts — no credentials required.

Ranking a week's posts by how many people actually saw them needs a reach
number, and the X API is not an option here: the bot's user context reads
``GET /2/users/me`` fine but every read of our own tweets answers **401
Unauthorized** (verified 2026-09-26 inside the running bot container), so
``non_public_metrics.impression_count`` is unreachable at the account's access
level. fxtwitter's public endpoint exposes ``views`` for any tweet, needs no
key, and is fast (measured 2026-09-26: 136 statuses in 5 s with 5 workers,
0 errors).

This is *presentation* data, so it must never be a reason a send fails: every
request is individually guarded, a hung burst is cut off by ``deadline_s``, and
callers get a (possibly partial) ``{post_id: views}`` map.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait

API_URL = "https://api.fxtwitter.com/PolitiUpdate/status/{id}"
STATUS_URL_RE = re.compile(
    r"^https?://(?:[\w-]+\.)*(?:x|twitter|fxtwitter)\.com/[^/\s]+/status/(\d+)"
)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

REQUEST_TIMEOUT_S = 15.0
DEADLINE_S = 120.0
WORKERS = 5
MAX_POSTS = 400
ATTEMPTS = 2


def parse_reach(payload: dict) -> int | None:
    """Pure: pull the view count out of an fxtwitter response, or None.

    Kept separate from the network call so the parsing rule is unit-testable
    without HTTP: anything unexpected (no tweet, a null/negative count, a
    non-numeric value) is "unknown", never 0 — an absent number must not look
    like "nobody read this" in the ranking.
    """
    tweet = (payload or {}).get("tweet") or {}
    views = tweet.get("views")
    if isinstance(views, bool) or not isinstance(views, (int, float)):
        return None
    if views < 0:
        return None
    return int(views)


def post_id_from_status_url(url: str) -> str | None:
    """Numeric status id from an x.com/twitter.com post URL (None otherwise).

    Deliberately strict: any other URL that merely ends in digits (an archive
    path like ``/uge/2026/38/``) must not be mistaken for a post id.
    """
    match = STATUS_URL_RE.match((url or "").strip())
    return match.group(1) if match else None


def _fetch_one(post_id: str, timeout: float) -> int | None:
    """One status lookup; returns None instead of raising (best-effort data)."""
    request = urllib.request.Request(
        API_URL.format(id=post_id),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                raw = response.read().decode("utf-8", "replace")
            return parse_reach(json.loads(raw))
        except Exception:  # noqa: BLE001 - reach is best-effort by design
            if attempt + 1 < ATTEMPTS:
                time.sleep(0.5 * (attempt + 1))
    return None


def fetch_views(
    post_ids: list[str | None],
    *,
    workers: int = WORKERS,
    timeout: float = REQUEST_TIMEOUT_S,
    deadline_s: float = DEADLINE_S,
    max_posts: int = MAX_POSTS,
) -> dict[str, int]:
    """Return ``{post_id: views}`` for the ids we could read.

    Missing/failed ids are simply absent from the result, so a caller can rank
    what it got and fall back to a view-independent layout for the rest. The
    id list is capped at ``max_posts`` and the whole burst at ``deadline_s`` so
    a slow or rate-limiting upstream can never stall the weekly job.
    """
    ids = [str(i) for i in post_ids if i][:max_posts]
    if not ids:
        return {}

    views: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_fetch_one, post_id, timeout): post_id for post_id in ids}
        done, pending = wait(list(futures), timeout=deadline_s)
        for future in done:
            try:
                value = future.result()
            except Exception:  # noqa: BLE001 - _fetch_one already guards, be safe
                value = None
            if value is not None:
                views[futures[future]] = value
        for future in pending:
            future.cancel()
    return views
