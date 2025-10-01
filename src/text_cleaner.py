from __future__ import annotations

import html
import re
from typing import Iterable

CITATION_PATTERN = re.compile(r"\[[0-9０-９]+\]")
REF_TAG_PATTERN = re.compile(r"<ref[^>]*?>.*?</ref>", re.IGNORECASE | re.DOTALL)
TEMPLATE_PATTERN = re.compile(r"\{\{.*?\}\}", re.DOTALL)
SECTION_PATTERN = re.compile(r"^=+\s*(.*?)\s*=+$", re.MULTILINE)
PAREN_REFERENCE_PATTERN = re.compile(r"（[0-9０-９]+）")
NOTE_REFERENCE_PATTERN = re.compile(
    r"（(?:注[:：]?\s*[0-9０-９]+|注[0-9０-９]+|脚注[:：]?\s*[0-9０-９]+|note\s*\d+)）",
    re.IGNORECASE,
)
BRACKETED_NOTE_PATTERN = re.compile(r"\([^\)]+?出典[^\)]*?\)")
ISBN_PATTERN = re.compile(r"ISBN(?:-1[03])?:?\s*[0-9０-９\-‐–−—ー\s]{10,30}", re.IGNORECASE)
NOISE_PARENTHESES_PATTERN = re.compile(r"（[^（）]{0,40}）")
NOISE_PAREN_KEYWORDS_JA: tuple[str, ...] = (
    "要出典",
    "出典不明",
    "要検証",
    "要更新",
    "要加筆",
    "要整理",
    "要補足",
    "編集者",
    "編集部",
    "出典の明記",
    "出典なし",
)
NOISE_PAREN_KEYWORDS_EN: tuple[str, ...] = (
    "citation needed",
    "editor",
    "to be added",
    "to be confirmed",
    "tbd",
)
CATALOG_CODE_PATTERNS = (
    re.compile(r"JASRAC作品コード[:：]?\s*[A-Z0-9\-／/]{3,}", re.IGNORECASE),
    re.compile(r"JASRAC番号[:：]?\s*[A-Z0-9\-／/]{3,}", re.IGNORECASE),
)
CATALOG_LINE_KEYWORDS = (
    "jasrac作品コード",
    "jasrac番号",
)
MULTI_SPACE_PATTERN = re.compile(r"[ \t\u3000]+")
NEWLINE_PATTERN = re.compile(r"\n{2,}")
BULLET_PREFIXES: tuple[str, ...] = ("・", "-", "*", "●", "■", "▲")
WIKIPEDIA_META_PREFIXES: tuple[str, ...] = (
    "出典",
    "脚注",
    "参考文献",
    "関連項目",
)


def _strip_wikipedia_metadata(lines: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in WIKIPEDIA_META_PREFIXES):
            continue
        if SECTION_PATTERN.match(stripped):
            continue
        if stripped.startswith("Category:") or stripped.startswith("カテゴリ:"):
            continue
        if stripped.startswith("[[") and stripped.endswith("]]"):
            # Skip bare link lines
            continue
        cleaned.append(stripped)
    return cleaned


def _normalise_bullets(lines: Iterable[str]) -> list[str]:
    normalised: list[str] = []
    for line in lines:
        stripped = line.strip()
        for prefix in BULLET_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix) :].strip()
                break
        normalised.append(stripped)
    return normalised


def _remove_catalog_codes(text: str) -> str:
    cleaned = text
    for pattern in CATALOG_CODE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def _filter_catalog_lines(lines: Iterable[str]) -> list[str]:
    filtered: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in CATALOG_LINE_KEYWORDS):
            continue
        filtered.append(line)
    return filtered


def _remove_noise_parentheses(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        inner = match.group()[1:-1].strip()
        if not inner:
            return " "

        inner_lower = inner.lower()
        if any(keyword in inner for keyword in NOISE_PAREN_KEYWORDS_JA):
            return " "
        if any(keyword in inner_lower for keyword in NOISE_PAREN_KEYWORDS_EN):
            return " "
        if re.fullmatch(r"(注|注記|注釈|脚注)[:：]?\s*[0-9０-９]*", inner):
            return " "
        if re.fullmatch(r"[0-9０-９a-zA-Z]{1,3}", inner):
            return " "
        return match.group()

    text = NOTE_REFERENCE_PATTERN.sub(" ", text)
    return NOISE_PARENTHESES_PATTERN.sub(replace, text)


def normalise_input_text(text: str) -> str:
    """Pre-process raw text to improve event extraction accuracy."""
    if not text:
        return ""

    text = html.unescape(text)
    text = _remove_catalog_codes(text)
    text = REF_TAG_PATTERN.sub(" ", text)
    text = TEMPLATE_PATTERN.sub(" ", text)
    text = CITATION_PATTERN.sub("", text)
    text = PAREN_REFERENCE_PATTERN.sub("", text)
    text = BRACKETED_NOTE_PATTERN.sub("", text)
    text = _remove_noise_parentheses(text)
    text = ISBN_PATTERN.sub(" ", text)

    lines = text.splitlines()
    lines = _strip_wikipedia_metadata(lines)
    lines = _filter_catalog_lines(lines)
    lines = _normalise_bullets(lines)

    cleaned = "\n".join(lines)
    cleaned = MULTI_SPACE_PATTERN.sub(" ", cleaned)
    cleaned = NEWLINE_PATTERN.sub("\n", cleaned)
    cleaned = cleaned.replace("・", " ・ ")
    cleaned = cleaned.replace("。", "。\n")
    cleaned = re.sub(r"[!?！？]", lambda m: f"{m.group()}\n", cleaned)

    cleaned = "\n".join(segment.strip() for segment in cleaned.splitlines() if segment.strip())
    return cleaned.strip()
