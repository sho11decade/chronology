from __future__ import annotations

import json
import logging
import time
from typing import Iterable, Optional

import requests
from requests import Response

try:  # pragma: no cover - 実行コンテキストにより相対/絶対が異なる
    from .settings import settings
except ImportError:  # pragma: no cover
    from settings import settings

logger = logging.getLogger("chronology.azure_ocr")

_DEFAULT_TIMEOUT_SECONDS = 15
_POLL_INTERVAL_SECONDS = 0.6
_LEGACY_LANGUAGE_AUTO = "unk"
_DEFAULT_IMAGE_ANALYSIS_VERSION = "2023-02-01-preview"
_FALLBACK_READ_VERSION = "v3.2"


class AzureVisionError(RuntimeError):
    """Azure Vision OCR 実行時の例外。"""


def is_configured() -> bool:
    """Azure Vision のエンドポイントとキーが設定されているか判定する。"""
    return bool(settings.azure_vision_endpoint and settings.azure_vision_key)


def extract_text_from_image(
    image_bytes: bytes,
    *,
    language: Optional[str] = None,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Azure Vision API を用いて画像からテキストを抽出する。"""
    if not is_configured():
        raise AzureVisionError("Azure Vision API の認証情報が設定されていません。")

    version = (settings.azure_vision_api_version or _DEFAULT_IMAGE_ANALYSIS_VERSION).strip()
    if not version:
        version = _DEFAULT_IMAGE_ANALYSIS_VERSION
    lang_param = _resolve_language(language)

    if _use_image_analysis_api(version):
        payload = _call_image_analysis_api(image_bytes, version, lang_param, timeout_seconds)
    else:
        payload = _call_read_api(image_bytes, version or _FALLBACK_READ_VERSION, lang_param, timeout_seconds)

    lines = list(_extract_lines(payload))
    text = "\n".join(line.strip() for line in lines if line and line.strip())
    if not text:
        raise AzureVisionError("OCR でテキストを抽出できませんでした。")
    return text


def _resolve_language(language: Optional[str]) -> Optional[str]:
    candidate = (language or settings.azure_vision_default_language or "").strip()
    if not candidate or candidate.lower() in {"auto", "automatic"}:
        return None
    return candidate


def _use_image_analysis_api(version: str) -> bool:
    return "-" in version or version.startswith("20")


def _call_image_analysis_api(
    image_bytes: bytes,
    version: str,
    language: Optional[str],
    timeout_seconds: int,
) -> dict:
    base = settings.azure_vision_endpoint.rstrip("/")
    url = f"{base}/computervision/imageanalysis:analyze"
    params = {"api-version": version, "features": "read"}
    if language:
        params["language"] = language
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_vision_key,
        "Content-Type": "application/octet-stream",
    }
    response = _send_request("POST", url, headers=headers, params=params, data=image_bytes, timeout=timeout_seconds)
    if response.status_code == 404:
        fallback_version = _FALLBACK_READ_VERSION
        logger.warning(
            "Azure Vision Image Analysis API not found (404). Falling back to Read API version %s.",
            fallback_version,
        )
        return _call_read_api(image_bytes, fallback_version, language, timeout_seconds)
    if response.status_code >= 400:
        _raise_azure_error(response)
    try:
        return response.json()
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise AzureVisionError("Azure Vision API の応答が不正です。") from exc


def _call_read_api(
    image_bytes: bytes,
    version: str,
    language: Optional[str],
    timeout_seconds: int,
) -> dict:
    if not version:
        version = _FALLBACK_READ_VERSION
    base = settings.azure_vision_endpoint.rstrip("/")
    url = f"{base}/vision/{version}/read/analyze"
    params = {}
    if language:
        params["language"] = language
    elif settings.azure_vision_default_language.lower() == "auto":
        params["language"] = _LEGACY_LANGUAGE_AUTO
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_vision_key,
        "Content-Type": "application/octet-stream",
    }
    response = _send_request("POST", url, headers=headers, params=params, data=image_bytes, timeout=timeout_seconds)
    if response.status_code != 202:
        _raise_azure_error(response)
    operation_url = response.headers.get("Operation-Location")
    if not operation_url:
        raise AzureVisionError("Azure Vision API から Operation-Location ヘッダーが返されませんでした。")

    deadline = time.time() + timeout_seconds
    poll_headers = {"Ocp-Apim-Subscription-Key": settings.azure_vision_key}
    while time.time() < deadline:
        poll_response = _send_request("GET", operation_url, headers=poll_headers, timeout=timeout_seconds)
        if poll_response.status_code >= 400:
            _raise_azure_error(poll_response)
        payload = poll_response.json()
        status = (payload.get("status") or "").lower()
        if status == "succeeded":
            return payload
        if status == "failed":
            raise AzureVisionError("Azure Vision OCR が失敗しました。")
        time.sleep(_POLL_INTERVAL_SECONDS)

    raise AzureVisionError("Azure Vision OCR の処理がタイムアウトしました。")


def _send_request(method: str, url: str, *, headers: dict, timeout: int, params: Optional[dict] = None, data: Optional[bytes] = None) -> Response:
    try:
        return requests.request(method, url, headers=headers, params=params, data=data, timeout=timeout)
    except requests.RequestException as exc:
        logger.exception("Azure Vision API call failed: %s", exc)
        raise AzureVisionError("Azure Vision API の呼び出しに失敗しました。") from exc


def _extract_lines(payload: dict) -> Iterable[str]:
    lines: list[str] = []

    def _append(text: Optional[str]) -> None:
        if text:
            cleaned = text.strip()
            if cleaned:
                lines.append(cleaned)

    analyze_result = payload.get("analyzeResult") or {}
    for page in analyze_result.get("readResults", []):
        for line in page.get("lines", []):
            _append(line.get("text") or line.get("content"))
    if not lines:
        _append(analyze_result.get("content"))

    read_result = payload.get("readResult") or {}
    for block in read_result.get("blocks", []):
        for line in block.get("lines", []):
            _append(line.get("text") or line.get("content"))
    for page in read_result.get("pages", []):  # 一部の API 形式では pages 配列が返る
        for line in page.get("lines", []):
            _append(line.get("text") or line.get("content"))
    if not lines:
        _append(read_result.get("content"))

    if not lines:
        _append(payload.get("content"))

    return lines


def _raise_azure_error(response: Response) -> None:
    message = f"Azure Vision API error: {response.status_code}"
    try:
        detail = response.json()
        message = f"{message} - {json.dumps(detail, ensure_ascii=False)}"
    except json.JSONDecodeError:
        message = f"{message} - {response.text}" if response.text else message
    raise AzureVisionError(message)


def has_ocr() -> bool:
    """従来のインターフェースに合わせたエイリアス。"""
    return is_configured()
