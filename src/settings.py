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
    # --- Cloudflare D1 / 共有機能設定 ---
    enable_sharing: bool = Field(
        default=True,
        description="共有機能を有効化するかどうか",
    )
    d1_enabled: bool = Field(
        default=False,
        description="Cloudflare D1 を使用する（True の場合、HTTP API 経由で実行）",
    )
    d1_account_id: str = Field(
        default="",
        description="Cloudflare アカウントID（D1 HTTP API 用）",
    )
    d1_database_id: str = Field(
        default="",
        description="Cloudflare D1 データベースID（UUID）",
    )
    d1_api_token: str = Field(
        default="",
        description="Cloudflare API トークン（D1 HTTP API 用）",
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
