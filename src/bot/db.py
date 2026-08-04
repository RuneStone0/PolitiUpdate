"""SQLite database for deduplication and post tracking."""

import os
import sqlite3
from datetime import datetime, timezone

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
            x_post_id   TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_posts_status
        ON posts (status)
        """
    )
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
) -> None:
    """Insert or update a post record."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO posts (guid, title, body, posted_at, status, x_post_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guid) DO UPDATE SET
            status = excluded.status,
            x_post_id = excluded.x_post_id,
            posted_at = excluded.posted_at
        """,
        (guid, title, body, now, status, x_post_id),
    )
    conn.commit()
    conn.close()


def get_failed_posts(limit: int = 5) -> list[dict]:
    """Return up to `limit` oldest failed posts for retry."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT guid, title FROM posts WHERE status = 'failed' ORDER BY posted_at ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [{"guid": r[0], "title": r[1]} for r in rows]
