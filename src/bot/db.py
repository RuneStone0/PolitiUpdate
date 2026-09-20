"""SQLite database for deduplication and post tracking."""

import difflib
import os
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from . import config


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            guid        TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            body        TEXT NOT NULL,
            posted_at   TEXT,
            status      TEXT NOT NULL DEFAULT 'pending',
            x_post_id   TEXT,
            pub_date    TEXT,
            district    TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_posts_status
        ON posts (status)
        """
    )
    # Tracks the exact text of every tweet we've successfully posted, so we
    # can recognize — before ever calling X — when a new item (possibly
    # under a different guid, e.g. a press release the feed re-published)
    # would duplicate one we already posted, instead of finding out via a
    # 403 from X after the fact.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS posted_texts (
            text        TEXT PRIMARY KEY,
            guid        TEXT NOT NULL,
            x_post_id   TEXT NOT NULL,
            posted_at   TEXT NOT NULL
        )
        """
    )
    # Migrate existing databases that pre-date the pub_date/district columns.
    for column in ("pub_date", "district"):
        try:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {column} TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()


def is_known(guid: str) -> bool:
    """Check if a guid has already been recorded."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM posts WHERE guid = ?", (guid,)
    ).fetchone()
    conn.close()
    return row is not None


def save_post(
    guid: str,
    title: str,
    body: str,
    status: str = "pending",
    x_post_id: str | None = None,
    pub_date: str | None = None,
    district: str | None = None,
) -> None:
    """Insert or update a post record."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO posts (guid, title, body, posted_at, status, x_post_id, pub_date, district)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guid) DO UPDATE SET
            status = excluded.status,
            x_post_id = excluded.x_post_id,
            posted_at = excluded.posted_at,
            pub_date = COALESCE(excluded.pub_date, pub_date),
            district = COALESCE(excluded.district, district)
        """,
        (guid, title, body, now, status, x_post_id, pub_date, district),
    )
    conn.commit()
    conn.close()


def find_posted_guid(text: str) -> str | None:
    """Return the guid this exact tweet text was already posted under, or
    None if it's never been posted."""
    conn = get_conn()
    row = conn.execute(
        "SELECT guid FROM posted_texts WHERE text = ?", (text,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def record_posted_texts(guid: str, pairs: Iterable[tuple[str, str | None]]) -> None:
    """Record the text of each successfully posted tweet in a thread, paired
    with its X post ID. Pairs with no id (a later item in the thread that
    failed to post) are skipped."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    for text, x_post_id in pairs:
        if not x_post_id or x_post_id == "dry-run":
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO posted_texts (text, guid, x_post_id, posted_at)
            VALUES (?, ?, ?, ?)
            """,
            (text, guid, x_post_id, now),
        )
    conn.commit()
    conn.close()


def get_failed_posts(limit: int = 5) -> list[dict]:
    """Return up to `limit` oldest failed posts for retry."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT guid, title, pub_date FROM posts WHERE status = 'failed' ORDER BY posted_at ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"guid": r[0], "title": r[1], "pub_date": r[2]} for r in rows]


def page_id(guid: str) -> str:
    """The press-release page a guid points at, ignoring its #sm-XXXXX update
    fragment. Two updates on one page are a thread, not duplicates."""
    return guid.split("#", 1)[0]


def _normalize_body(body: str) -> str:
    return " ".join(body.split()).lower()


def find_recent_similar_post(
    body: str,
    exclude_guid: str,
    within_hours: float = 24,
    threshold: float = 0.95,
) -> dict | None:
    """Find a recently posted row whose body is near-identical to `body`.

    Compares the *scraped body*, not the tweet text: when the feed re-publishes
    an update under a new pressemeddelelse id, the two entries share the body
    but can differ in the district prefix, so the exact-tweet-text check in
    `find_posted_guid()` misses them and the story posts twice.

    Rows from the same press release (`exclude_guid`'s page) are ignored — those
    are the legitimate updates/replies of one thread.

    `threshold` defaults to near-identity on purpose: below ~0.98 the matches
    include re-published *corrections* (a missing person's name scrubbed after
    they are found), which must not be suppressed. See config.CONTENT_DEDUPE_*.

    Returns a dict with the matching row and `similarity`, or None.
    """
    if not body or not body.strip():
        return None

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=within_hours)).isoformat()
    page = page_id(exclude_guid)
    needle = _normalize_body(body)

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT guid, title, body, posted_at, x_post_id FROM posts
        WHERE status = 'posted' AND posted_at >= ?
        ORDER BY posted_at DESC
        """,
        (cutoff,),
    ).fetchall()
    conn.close()

    for guid, title, other_body, posted_at, x_post_id in rows:
        if page_id(guid) == page or not other_body:
            continue
        ratio = difflib.SequenceMatcher(
            None, needle, _normalize_body(other_body), autojunk=False
        ).ratio()
        if ratio >= threshold:
            return {
                "guid": guid,
                "title": title,
                "posted_at": posted_at,
                "x_post_id": x_post_id,
                "similarity": ratio,
            }

    return None
