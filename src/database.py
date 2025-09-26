from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .models import TimelineItem

DEFAULT_DB_PATH = Path(os.getenv("CHRONOLOGY_DB_PATH", Path(__file__).parent / "chronology.db"))

SCHEMA_REQUESTS = """
CREATE TABLE IF NOT EXISTS timeline_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    input_preview TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    total_events INTEGER NOT NULL
);
"""

SCHEMA_ITEMS = """
CREATE TABLE IF NOT EXISTS timeline_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    date_text TEXT,
    date_iso TEXT,
    title TEXT,
    description TEXT,
    category TEXT,
    importance REAL,
    people TEXT,
    locations TEXT,
    FOREIGN KEY(request_id) REFERENCES timeline_requests(id) ON DELETE CASCADE
);
"""


@contextmanager
def _get_connection(db_path: Optional[Path] = None):
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    with _get_connection(db_path) as conn:
        conn.execute(SCHEMA_REQUESTS)
        conn.execute(SCHEMA_ITEMS)


def store_timeline(
    input_text: str,
    items: Iterable[TimelineItem],
    *,
    source: str = "api",
    db_path: Optional[Path] = None,
) -> int:
    items_list = list(items)
    generated_at = datetime.utcnow().isoformat()
    preview = (input_text or "").strip().replace("\n", " ")[:200]

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO timeline_requests (source, input_preview, generated_at, total_events) VALUES (?, ?, ?, ?)",
            (source, preview, generated_at, len(items_list)),
        )
        request_id_raw = cursor.lastrowid
        if request_id_raw is None:  # pragma: no cover - sqlite should always return an id
            raise RuntimeError("Failed to persist timeline request")
        request_id = int(request_id_raw)
        conn.executemany(
            """
            INSERT INTO timeline_items (
                request_id, item_id, date_text, date_iso, title, description, category, importance, people, locations
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    request_id,
                    item.id,
                    item.date_text,
                    item.date_iso,
                    item.title,
                    item.description,
                    item.category,
                    float(item.importance),
                    json.dumps(item.people, ensure_ascii=False),
                    json.dumps(item.locations, ensure_ascii=False),
                )
                for item in items_list
            ],
        )
    return request_id


def fetch_recent_timelines(
    limit: int = 10,
    *,
    db_path: Optional[Path] = None,
) -> List[Tuple[int, datetime, int, str]]:
    with _get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, generated_at, total_events, input_preview
            FROM timeline_requests
            ORDER BY datetime(generated_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        (
            int(row["id"]),
            datetime.fromisoformat(row["generated_at"]),
            int(row["total_events"]),
            row["input_preview"],
        )
        for row in rows
    ]


def fetch_timeline(
    request_id: int,
    *,
    db_path: Optional[Path] = None,
) -> Tuple[Optional[datetime], List[TimelineItem]]:
    with _get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        header = conn.execute(
            "SELECT generated_at FROM timeline_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if header is None:
            return None, []
        rows = conn.execute(
            """
            SELECT item_id, date_text, date_iso, title, description, category, importance, people, locations
            FROM timeline_items
            WHERE request_id = ?
            ORDER BY id ASC
            """,
            (request_id,),
        ).fetchall()

    generated_at = datetime.fromisoformat(header["generated_at"])
    items = [
        TimelineItem(
            id=row["item_id"],
            date_text=row["date_text"] or "",
            date_iso=row["date_iso"],
            title=row["title"] or "",
            description=row["description"] or "",
            category=row["category"] or "general",
            importance=float(row["importance"] or 0.0),
            people=json.loads(row["people"] or "[]"),
            locations=json.loads(row["locations"] or "[]"),
        )
        for row in rows
    ]
    return generated_at, items
