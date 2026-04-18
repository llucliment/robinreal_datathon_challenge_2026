from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db import get_connection

# Regenerate profile every N new interactions since last generation
_REGEN_THRESHOLD = 5


def create_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS user_interactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT    NOT NULL,
            event_type  TEXT    NOT NULL,
            listing_id  TEXT,
            query       TEXT,
            session_id  TEXT,
            created_at  TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ui_user_id ON user_interactions(user_id);

        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id           TEXT PRIMARY KEY,
            profile_json      TEXT NOT NULL,
            interaction_count INTEGER NOT NULL DEFAULT 0,
            generated_at      TEXT NOT NULL
        );
    """)
    connection.commit()


def log_interaction(
    db_path: Path,
    *,
    user_id: str,
    event_type: str,
    listing_id: str | None = None,
    query: str | None = None,
    session_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO user_interactions
               (user_id, event_type, listing_id, query, session_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, event_type, listing_id, query, session_id, now),
        )
        conn.commit()


def get_interactions(db_path: Path, user_id: str, limit: int = 200) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """SELECT event_type, listing_id, query, created_at
               FROM user_interactions
               WHERE user_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_profile(db_path: Path, user_id: str) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT profile_json, interaction_count FROM user_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["profile_json"])


def save_profile(db_path: Path, user_id: str, profile: dict[str, Any], interaction_count: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    profile["generated_at"] = now
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO user_profiles (user_id, profile_json, interaction_count, generated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 profile_json      = excluded.profile_json,
                 interaction_count = excluded.interaction_count,
                 generated_at      = excluded.generated_at""",
            (user_id, json.dumps(profile), interaction_count, now),
        )
        conn.commit()


def needs_regen(db_path: Path, user_id: str) -> bool:
    """True if enough new interactions have arrived to warrant a fresh profile."""
    with get_connection(db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM user_interactions WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        row = conn.execute(
            "SELECT interaction_count FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    last_count = row["interaction_count"] if row else 0
    return (total - last_count) >= _REGEN_THRESHOLD or row is None
