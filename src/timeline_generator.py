from __future__ import annotations

import itertools
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional
from uuid import uuid4

# Add current directory to Python path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from .text_features import LOCATION_KEYWORDS, PEOPLE_SUFFIXES, CATEGORY_KEYWORDS
    from .models import TimelineItem
    from .japanese_calendar import normalise_era_notation
except ImportError:
    # Fallback to absolute imports when running as script
    from text_features import LOCATION_KEYWORDS, PEOPLE_SUFFIXES, CATEGORY_KEYWORDS
    from models import TimelineItem
    from japanese_calendar import normalise_era_notation

DATE_PATTERNS = [
    re.compile(r"(?P<year>\d{3,4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日?"),
    re.compile(r"(?P<year>\d{3,4})年(?P<month>\d{1,2})月"),
    re.compile(r"(?P<year>\d{3,4})年"),
    re.compile(r"(?P<year>\d{3,4})月(?P<day>\d{1,2})日"),
    re.compile(r"(?P<year>\d{3,4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"),
    re.compile(r"(?P<year>\d{3,4})/(?P<month>\d{1,2})/(?P<day>\d{1,2})"),
]

ERA_PATTERN = re.compile(r"(?P<era>令和|平成|昭和|大正|明治)(?P<year>[0-9０-９]+|元)年(?:(?P<month>[0-9０-９]+)月)?(?:(?P<day>[0-9０-９]+)日)?")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!\?])\s*")


@dataclass
class RawEvent:
    sentence: str
    date_text: str
    date_iso: Optional[str]


def split_sentences(text: str) -> List[str]:
    stripped = text.replace("\r", "")
    sentences = [
        segment.strip()
        for segment in SENTENCE_SPLIT_PATTERN.split(stripped)
        if segment.strip()
    ]
    if not sentences:
        sentences = [stripped.strip()]
    return sentences


def iter_dates(sentence: str) -> Iterable[RawEvent]:
    for match in ERA_PATTERN.finditer(sentence):
        era_raw = match.group()
        iso_candidate = normalise_era_notation(era_raw)
        yield RawEvent(sentence=sentence, date_text=era_raw, date_iso=iso_candidate)

    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(sentence):
            year = int(match.group("year"))
            month = int(match.group("month")) if match.groupdict().get("month") else 1
            day = int(match.group("day")) if match.groupdict().get("day") else 1
            iso = date(year, min(month, 12), min(day, 28)).isoformat()
            yield RawEvent(
                sentence=sentence,
                date_text=match.group(),
                date_iso=iso,
            )


def detect_people(tokens: List[str]) -> List[str]:
    candidates: List[str] = []
    for token in tokens:
        if any(token.endswith(suffix) for suffix in PEOPLE_SUFFIXES):
            candidates.append(token)
        elif len(token) >= 2 and all("\u4e00" <= char <= "\u9fff" for char in token):
            candidates.append(token)
    return sorted(set(candidates))[:5]


def detect_locations(sentence: str) -> List[str]:
    hits = [word for word in LOCATION_KEYWORDS if word in sentence]
    return sorted(set(hits))[:5]


def infer_category(sentence: str) -> str:
    lowercase = sentence.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowercase for keyword in keywords):
            return category
    return "general"


def score_importance(sentence: str) -> float:
    words = re.findall(r"[\w一-龥]+", sentence.lower())
    keyword_counts = Counter(words)
    emphasis = sum(
        keyword_counts.get(keyword, 0)
        for keywords in CATEGORY_KEYWORDS.values()
        for keyword in keywords
    )
    length_bonus = min(len(sentence) / 120.0, 1.0)
    score = min(1.0, 0.3 + 0.2 * emphasis + 0.5 * length_bonus)
    return round(score, 2)


def extract_tokens(sentence: str) -> List[str]:
    return re.findall(r"[\w一-龥]+", sentence)


def build_title(sentence: str, date_text: str) -> str:
    if sentence.startswith(date_text):
        remainder = sentence[len(date_text) :].strip("。:： ")
        if remainder:
            return remainder[:40]
    return sentence[:40]


def generate_timeline(text: str, max_events: int = 150) -> List[TimelineItem]:
    sentences = split_sentences(text)

    raw_events: List[RawEvent] = []
    for sentence in sentences:
        matches = list(iter_dates(sentence))
        if not matches:
            continue
        raw_events.extend(matches)

    # Deduplicate by sentence/date combo to avoid repetition when multiple regexes match
    unique_events = list({(event.sentence, event.date_text): event for event in raw_events}.values())

    items: List[TimelineItem] = []
    for event in itertools.islice(unique_events, 0, max_events):
        tokens = extract_tokens(event.sentence)
        people = detect_people(tokens)
        locations = detect_locations(event.sentence)
        category = infer_category(event.sentence)
        importance = score_importance(event.sentence)
        title = build_title(event.sentence, event.date_text)
        item = TimelineItem(
            id=str(uuid4()),
            date_text=event.date_text,
            date_iso=event.date_iso,
            title=title,
            description=event.sentence,
            people=people,
            locations=locations,
            category=category,
            importance=importance,
        )
        items.append(item)

    items.sort(key=lambda item: (item.date_iso or "9999-12-31", item.importance * -1))
    return items
