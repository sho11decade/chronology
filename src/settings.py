from __future__ import annotations

import logging
import json
from typing import List

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_title: str = Field(default="Chronology Maker API", description="FastAPI application title")
    app_description: str = Field(
        default="テキストから年表を生成するためのAPI",
        description="OpenAPI 用の説明文",
    )
    allowed_origins: List[str] = Field(
        default_factory=lambda: ["*"],
        description="CORS で許可するオリジンの一覧",
    )
    log_level: str = Field(
        default="INFO",
        description="アプリケーションログのレベル (DEBUG/INFO/WARNING/ERROR/CRITICAL)",
    )
    enable_request_logging: bool = Field(
        default=True,
        description="各リクエストのログ出力を有効化",
    )
    azure_vision_endpoint: str = Field(
        default="",
        description="Azure AI Vision のエンドポイント URL（例: https://example.cognitiveservices.azure.com/）",
    )
    azure_vision_key: str = Field(
        default="",
        description="Azure AI Vision の API キー",
    )
    azure_vision_api_version: str = Field(
        default="2023-02-01-preview",
        description="Azure AI Vision Read API のバージョン",
    )
    azure_vision_default_language: str = Field(
        default="ja",
        description="OCR の既定言語コード。auto を指定すると自動判定。",
    )
    # --- 共有機能設定（Firestore / SQLite フォールバック） ---
    enable_sharing: bool = Field(
        default=True,
        description="共有機能を有効化するかどうか",
    )
    share_ttl_days: int = Field(
        default=30,
        description="共有の有効期限（日単位）。既定は30日",
        ge=1,
        le=3650,
    )
    max_input_characters: int = Field(
        default=200_000,
        description="入力テキストの最大文字数上限。共有・生成・検索すべてに適用",
        ge=10_000,
        le=1_000_000,
    )
    max_timeline_events: int = Field(
        default=500,
        description="年表生成時に保持する最大イベント数",
        ge=50,
        le=5_000,
    )
    max_search_results: int = Field(
        default=500,
        description="検索レスポンスとして返却する最大件数の上限",
        ge=50,
        le=5_000,
    )
    firestore_enabled: bool = Field(
        default=False,
        description="Firestore を使用して共有データを保存するかどうか",
    )
    firestore_project_id: str = Field(
        default="",
        description="Firestore クライアントで使用する GCP プロジェクトID（省略可）",
    )
    firestore_credentials_path: str = Field(
        default="",
        description="サービスアカウントJSONのパス。空の場合は Application Default Credentials を利用",
    )
    firestore_collection: str = Field(
        default="shares",
        description="共有ドキュメントを格納する Firestore コレクション名",
    )
    public_base_url: str = Field(
        default="",
        description="クライアント向けの公開ベースURL。共有URL生成に使用（例: https://example.com）",
    )

    class Config:
        env_prefix = "CHRONOLOGY_"
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"

        @classmethod
        def parse_env_var(cls, field_name, raw_value):  # type: ignore[override]
            """
            環境変数をPython値へ変換する。
            既定（pydantic v1）は JSON として解釈するため、
            List[str] をカンマ区切りや "*" 単体で渡したいケースに対応する。
            """
            try:
                # まずは通常通り JSON として解釈（true/false, 数値, 配列に対応）
                return json.loads(raw_value)
            except Exception:
                # JSON でなければ、フィールド個別のフォールバック
                if field_name == "allowed_origins":
                    raw = str(raw_value).strip()
                    if raw == "*":
                        return ["*"]
                    # カンマ区切り対応
                    return [v.strip() for v in raw.split(",") if v and v.strip()]
                # デフォルトは生の文字列を返す
                return raw_value

    @validator("allowed_origins", pre=True)
    def _split_origins(cls, value):  # type: ignore[override]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @validator("log_level")
    def _normalise_log_level(cls, value: str) -> str:  # type: ignore[override]
        candidate = value.upper()
        if candidate not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            logging.getLogger("chronology.settings").warning(
                "Unknown log level '%s', falling back to INFO.", value
            )
            return "INFO"
        return candidate


settings = Settings()
