from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import requests


@dataclass
class D1Config:
    enabled: bool
    account_id: str
    database_id: str
    api_token: str


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def plus_days_utc_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


class ShareStore:
    """
    共有データの永続化レイヤ。
    - Cloudflare D1 が有効な場合: D1 HTTP API を使用
    - 無効な場合: ローカル SQLite ファイルに保存（./data/chronology.db）
    """

    def __init__(self, d1: D1Config | None = None, db_path: Optional[str] = None):
        self._d1 = d1 or D1Config(False, "", "", "")
        self._db_path = db_path or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "chronology.db"))
        if not self._d1.enabled:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self.init_schema()

    # -------------------------------
    # Public API
    # -------------------------------
    def create_share(
        self,
        text: str,
        title: str,
        items: list[dict[str, Any]],
        expires_at_iso: Optional[str] = None,
    ) -> tuple[str, str, str]:
        """
        共有を作成。
        Returns: (share_id, created_at_iso, expires_at_iso)
        """
        share_id = str(uuid4())
        created_at = now_utc_iso()
        expires_at = expires_at_iso or plus_days_utc_iso(30)
        items_json = json.dumps(items, ensure_ascii=False)
        if self._d1.enabled:
            self._d1_execute(
                """
                INSERT INTO shares (id, title, text, items_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [share_id, title, text, items_json, created_at, expires_at],
            )
        else:
            with self._sqlite_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shares (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        text TEXT NOT NULL,
                        items_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO shares (id, title, text, items_json, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (share_id, title, text, items_json, created_at, expires_at),
                )
        return share_id, created_at, expires_at

    def get_share(self, share_id: str) -> Optional[Dict[str, Any]]:
        if self._d1.enabled:
            rows = self._d1_query(
                "SELECT id, title, text, items_json, created_at, expires_at FROM shares WHERE id = ? LIMIT 1",
                [share_id],
            )
            row = rows[0] if rows else None
            if not row:
                return None
            items = json.loads(row[3]) if row[3] else []
            return {
                "id": row[0],
                "title": row[1],
                "text": row[2],
                "items": items,
                "created_at": row[4],
                "expires_at": row[5],
            }
        else:
            with self._sqlite_conn() as conn:
                cur = conn.execute(
                    "SELECT id, title, text, items_json, created_at, expires_at FROM shares WHERE id = ? LIMIT 1",
                    (share_id,),
                )
                r = cur.fetchone()
            if not r:
                return None
            items = json.loads(r[3]) if r[3] else []
            return {
                "id": r[0],
                "title": r[1],
                "text": r[2],
                "items": items,
                "created_at": r[4],
                "expires_at": r[5],
            }

    def init_schema(self) -> None:
        if self._d1.enabled:
            # D1: IF NOT EXISTS で初期化 → 既存にexpires_atが無ければ追加
            self._d1_execute(
                """
                CREATE TABLE IF NOT EXISTS shares (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    items_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """,
                [],
            )
            try:
                self._d1_execute(
                    "ALTER TABLE shares ADD COLUMN expires_at TEXT NOT NULL",
                    [],
                )
            except Exception:
                # 既に列がある場合などは無視
                pass
        else:
            with self._sqlite_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shares (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        text TEXT NOT NULL,
                        items_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )
                    """
                )
                # 既存テーブルに列が無い場合は追加
                cur = conn.execute("PRAGMA table_info(shares)")
                cols = [row[1] for row in cur.fetchall()]
                if "expires_at" not in cols:
                    conn.execute("ALTER TABLE shares ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''")

    # -------------------------------
    # Private helpers
    # -------------------------------
    def _sqlite_conn(self):
        return sqlite3.connect(self._db_path)

    def _d1_base(self) -> str:
        return f"https://api.cloudflare.com/client/v4/accounts/{self._d1.account_id}/d1/database/{self._d1.database_id}/query"

    def _d1_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._d1.api_token}",
            "Content-Type": "application/json",
        }

    def _d1_query(self, sql: str, params: list[Any] | None = None) -> list[list[Any]]:
        payload: dict[str, Any] = {"sql": sql}
        if params:
            payload["params"] = params
        resp = requests.post(self._d1_base(), headers=self._d1_headers(), json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", False):
            raise RuntimeError(f"D1 query failed: {data}")
        # D1 returns results in data['result'][0]['results'] as array of objects keyed by column names.
        result_sets = data.get("result") or []
        if not result_sets:
            return []
        first = result_sets[0]
        rows = first.get("results") or []
        # Convert dict rows to list ordered by select columns index; since we can't know reliably,
        # keep values order by dict iteration (Python 3.7+ preserves insertion which matches D1 order).
        return [list(row.values()) for row in rows]

    def _d1_execute(self, sql: str, params: list[Any] | None = None) -> None:
        payload: dict[str, Any] = {"sql": sql}
        if params:
            payload["params"] = params
        resp = requests.post(self._d1_base(), headers=self._d1_headers(), json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", False):
            raise RuntimeError(f"D1 execute failed: {data}")
