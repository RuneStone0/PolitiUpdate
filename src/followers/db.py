"""SQLite database tracking who follows us and who we've followed back."""

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
        CREATE TABLE IF NOT EXISTS followers (
            user_id       TEXT PRIMARY KEY,
            username      TEXT NOT NULL,
            followed_back INTEGER NOT NULL DEFAULT 0,
            first_seen    TEXT NOT NULL,
            last_seen     TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def get_known_ids() -> set[str]:
    """Return the set of user_ids we currently track as followers."""
    conn = get_conn()
    rows = conn.execute("SELECT user_id FROM followers").fetchall()
    conn.close()
    return {r[0] for r in rows}


def get_follower(user_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT user_id, username, followed_back FROM followers WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {"user_id": row[0], "username": row[1], "followed_back": bool(row[2])}


def upsert_follower(user_id: str, username: str, followed_back: bool) -> None:
    """Insert or update a tracked follower. followed_back is sticky (never unset here)."""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO followers (user_id, username, followed_back, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            followed_back = followed_back OR excluded.followed_back,
            last_seen = excluded.last_seen
        """,
        (user_id, username, int(followed_back), now, now),
    )
    conn.commit()
    conn.close()


def mark_followed_back(user_id: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE followers SET followed_back = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def remove_follower(user_id: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM followers WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
