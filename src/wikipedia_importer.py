from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, unquote, urlparse

import requests
from fastapi import HTTPException

try:  # pragma: no cover - imported dynamically during tests
    from .text_extractor import MAX_CHARACTERS
except ImportError:  # pragma: no cover - fallback when running as script
    from text_extractor import MAX_CHARACTERS

USER_AGENT = "ChronologyImporter/0.1 (+https://github.com/)"
REQUEST_TIMEOUT = 10
_LANGUAGE_PATTERN = re.compile(r"^[a-zA-Z\-]{2,12}$")


@dataclass
class WikipediaArticle:
    title: str
    language: str
    url: str
    text: str
    preview: str

    @property
    def characters(self) -> int:
        return len(self.text)


def fetch_wikipedia_article(
    *,
    topic: Optional[str] = None,
    url: Optional[str] = None,
    language: str = "ja",
) -> WikipediaArticle:
    """Fetch plain text from Wikipedia using the public API.

    Parameters
    ----------
    topic: Optional[str]
        Page title to look up (e.g. "坂本龍馬").
    url: Optional[str]
        Full Wikipedia URL. When provided it overrides `language` and `topic`.
    language: str
        MediaWiki language code (default: "ja").
    """

    resolved_language, resolved_title = _resolve_page_identity(topic=topic, url=url, language=language)
    title, text = _retrieve_page(resolved_language, resolved_title)

    cleaned_text = text.strip()
    if not cleaned_text:
        raise HTTPException(status_code=404, detail="Wikipediaページから本文を取得できませんでした。")

    if len(cleaned_text) > MAX_CHARACTERS:
        cleaned_text = cleaned_text[:MAX_CHARACTERS]

    preview = cleaned_text[:200].replace("\n", " ")
    canonical_url = _build_canonical_url(resolved_language, title)

    return WikipediaArticle(
        title=title,
        language=resolved_language,
        url=canonical_url,
        text=cleaned_text,
        preview=preview,
    )


def _resolve_page_identity(
    *,
    topic: Optional[str],
    url: Optional[str],
    language: str,
) -> tuple[str, str]:
    if url:
        return _extract_from_url(url)

    if not topic:
        raise HTTPException(status_code=400, detail="WikipediaのトピックまたはURLを指定してください。")

    normalised_language = _normalise_language(language)
    normalised_title = topic.strip()
    if not normalised_title:
        raise HTTPException(status_code=400, detail="Wikipediaのトピックが空です。")

    return normalised_language, normalised_title


def _extract_from_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if not parsed.scheme.startswith("http") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="有効な Wikipedia のURLを指定してください。")

    hostname_parts = parsed.hostname.split(".") if parsed.hostname else []
    if len(hostname_parts) < 3 or hostname_parts[-2:] != ["wikipedia", "org"]:
        raise HTTPException(status_code=400, detail="Wikipedia ドメインのURLを指定してください。")

    language = _normalise_language(hostname_parts[0])

    if not parsed.path.startswith("/wiki/"):
        raise HTTPException(status_code=400, detail="Wikipedia の記事URLを指定してください。")

    title = unquote(parsed.path[len("/wiki/") :])
    if not title:
        raise HTTPException(status_code=400, detail="Wikipedia の記事タイトルを解析できませんでした。")

    return language, title


def _normalise_language(language: str) -> str:
    candidate = (language or "ja").strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="言語コードが空です。")
    if not _LANGUAGE_PATTERN.match(candidate):
        raise HTTPException(status_code=400, detail="言語コードの形式が正しくありません。")
    return candidate.lower()


def _build_canonical_url(language: str, title: str) -> str:
    quoted = quote(title.replace(" ", "_"))
    return f"https://{language}.wikipedia.org/wiki/{quoted}"


def _retrieve_page(language: str, title: str) -> tuple[str, str]:
    endpoint = f"https://{language}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "exsectionformat": "plain",
        "titles": title,
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    }
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(endpoint, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail="Wikipedia API への接続に失敗しました。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Wikipedia API のレスポンス解析に失敗しました。") from exc

    pages = data.get("query", {}).get("pages") or []
    if not pages:
        raise HTTPException(status_code=404, detail="指定した記事が見つかりませんでした。")

    page = pages[0]
    if page.get("missing"):
        raise HTTPException(status_code=404, detail="指定した記事が見つかりませんでした。")

    extract = (page.get("extract") or "").strip()
    if not extract:
        raise HTTPException(status_code=404, detail="記事本文を取得できませんでした。")

    resolved_title = page.get("title") or title
    return resolved_title, extract
