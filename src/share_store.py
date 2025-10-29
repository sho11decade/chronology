from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

try:  # pragma: no cover - optional dependency for Firestore mode
    from google.cloud import firestore as firestore_client  # type: ignore
except ImportError:  # pragma: no cover - fall back to SQLite only
    firestore_client = None

try:  # pragma: no cover - created lazily when credentials file is provided
    from google.oauth2 import service_account  # type: ignore
except ImportError:  # pragma: no cover - handled when Firestore credentials are required
    service_account = None


@dataclass
class FirestoreConfig:
    enabled: bool
    project_id: str = ""
    credentials_path: str = ""
    collection: str = "shares"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def plus_days_utc_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


class ShareStore:
    """
    共有データの永続化レイヤ。
    - Firestore を有効にした場合: 指定コレクションへドキュメント保存
    - 無効時: ローカル SQLite ファイルに保存（./data/chronology.db）
    """

    def __init__(self, firestore: FirestoreConfig | None = None, db_path: Optional[str] = None):
        self._firestore_cfg = firestore or FirestoreConfig(False)
        self._firestore_client = None
        self._firestore_collection = self._firestore_cfg.collection or "shares"
        if self._firestore_cfg.enabled:
            if firestore_client is None:
                raise RuntimeError(
                    "Firestore モードが有効ですが google-cloud-firestore がインストールされていません。"
                )
            credentials = None
            creds_path = (self._firestore_cfg.credentials_path or "").strip()
            if creds_path:
                if service_account is None:
                    raise RuntimeError("Firestore 認証用に google-auth が必要です。")
                credentials = service_account.Credentials.from_service_account_file(creds_path)
            project_id = (self._firestore_cfg.project_id or "").strip() or None
            self._firestore_client = firestore_client.Client(project=project_id, credentials=credentials)
            self._db_path = None
        else:
            self._db_path = db_path or os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "data", "chronology.db")
            )
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
        if self._firestore_client:
            payload = {
                "id": share_id,
                "title": title,
                "text": text,
                "items": items,
                "created_at": created_at,
                "expires_at": expires_at,
            }
            self._firestore_client.collection(self._firestore_collection).document(share_id).set(payload)
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
        if self._firestore_client:
            doc_ref = self._firestore_client.collection(self._firestore_collection).document(share_id)
            try:
                snapshot = doc_ref.get()
            except Exception as exc:  # pragma: no cover - surface Firestore failure
                raise RuntimeError("Firestore から共有データを取得できませんでした。") from exc
            if not snapshot.exists:
                return None
            data = snapshot.to_dict() or {}
            return {
                "id": data.get("id", share_id),
                "title": data.get("title", ""),
                "text": data.get("text", ""),
                "items": data.get("items", []) or [],
                "created_at": data.get("created_at", now_utc_iso()),
                "expires_at": data.get("expires_at", now_utc_iso()),
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
        if self._firestore_client:
            # Firestore はスキーマレスのため初期化不要。
            return
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
        if not self._db_path:
            raise RuntimeError("SQLite モードが無効です。")
        return sqlite3.connect(self._db_path)
