from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import get_connection


def ensure_user(db_path: Path, user_id: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, display_name) VALUES (?, ?)",
            [user_id, user_id],
        )
        conn.commit()


def save_query(
    db_path: Path,
    user_id: str,
    query: str,
    soft_facts: dict[str, Any],
    hard_facts: dict[str, Any],
) -> None:
    ensure_user(db_path, user_id)
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_query_history (user_id, query, soft_facts_json, hard_facts_json)
            VALUES (?, ?, ?, ?)
            """,
            [user_id, query, json.dumps(soft_facts), json.dumps(hard_facts)],
        )
        conn.commit()


def get_history(db_path: Path, user_id: str, limit: int = 30) -> list[dict[str, Any]]:
    """Return the user's most recent queries, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT query, soft_facts_json, hard_facts_json, created_at
            FROM user_query_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [user_id, limit],
        ).fetchall()

    return [
        {
            "query": row["query"],
            "soft_facts": json.loads(row["soft_facts_json"]),
            "hard_facts": json.loads(row["hard_facts_json"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
