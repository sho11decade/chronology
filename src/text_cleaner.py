from __future__ import annotations

import html
import re
from typing import Iterable

CITATION_PATTERN = re.compile(r"\[[0-9０-９]+\]")
REF_TAG_PATTERN = re.compile(r"<ref[^>]*?>.*?</ref>", re.IGNORECASE | re.DOTALL)
TEMPLATE_PATTERN = re.compile(r"\{\{.*?\}\}", re.DOTALL)
SECTION_PATTERN = re.compile(r"^=+\s*(.*?)\s*=+$", re.MULTILINE)
PAREN_REFERENCE_PATTERN = re.compile(r"（[0-9０-９]+）")
BRACKETED_NOTE_PATTERN = re.compile(r"\([^\)]+?出典[^\)]*?\)")
ISBN_PATTERN = re.compile(r"ISBN(?:-1[03])?:?\s*[0-9０-９\-‐–−—ー\s]{10,30}", re.IGNORECASE)
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


def normalise_input_text(text: str) -> str:
    """Pre-process raw text to improve event extraction accuracy."""
    if not text:
        return ""

    text = html.unescape(text)
    text = REF_TAG_PATTERN.sub(" ", text)
    text = TEMPLATE_PATTERN.sub(" ", text)
    text = CITATION_PATTERN.sub("", text)
    text = PAREN_REFERENCE_PATTERN.sub("", text)
    text = BRACKETED_NOTE_PATTERN.sub("", text)
    text = ISBN_PATTERN.sub(" ", text)

    lines = text.splitlines()
    lines = _strip_wikipedia_metadata(lines)
    lines = _normalise_bullets(lines)

    cleaned = "\n".join(lines)
    cleaned = MULTI_SPACE_PATTERN.sub(" ", cleaned)
    cleaned = NEWLINE_PATTERN.sub("\n", cleaned)
    cleaned = cleaned.replace("・", " ・ ")
    cleaned = cleaned.replace("。", "。\n")
    cleaned = re.sub(r"[!?！？]", lambda m: f"{m.group()}\n", cleaned)

    cleaned = "\n".join(segment.strip() for segment in cleaned.splitlines() if segment.strip())
    return cleaned.strip()
