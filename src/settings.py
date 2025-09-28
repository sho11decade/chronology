from __future__ import annotations

import logging
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

    class Config:
        env_prefix = "CHRONOLOGY_"
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"

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
