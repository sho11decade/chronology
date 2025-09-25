from __future__ import annotations

import itertools
import math
import re
import sys
from calendar import monthrange
from collections import Counter, OrderedDict
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

DIGIT_CLASS = "0-9０-９"

DATE_PATTERNS = [
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})年(?P<month>[{DIGIT_CLASS}]{{1,2}})月(?P<day>[{DIGIT_CLASS}]{{1,2}})日?"),
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})年(?P<month>[{DIGIT_CLASS}]{{1,2}})月"),
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})年"),
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})月(?P<day>[{DIGIT_CLASS}]{{1,2}})日"),
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})[-/\.](?P<month>[{DIGIT_CLASS}]{{1,2}})[-/\.](?P<day>[{DIGIT_CLASS}]{{1,2}})"),
]

ERA_PATTERN = re.compile(r"(?P<era>令和|平成|昭和|大正|明治)(?P<year>[0-9０-９]+|元)年(?:(?P<month>[0-9０-９]+)月)?(?:(?P<day>[0-9０-９]+)日)?")

FULLWIDTH_DIGIT_TABLE = str.maketrans({
    "０": "0",
    "１": "1",
    "２": "2",
    "３": "3",
    "４": "4",
    "５": "5",
    "６": "6",
    "７": "7",
    "８": "8",
    "９": "9",
})
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


def _normalise_digits(value: str) -> str:
    return value.translate(FULLWIDTH_DIGIT_TABLE)


def _parse_number(value: Optional[str], fallback: int = 1) -> int:
    if value is None:
        return fallback
    try:
        return int(_normalise_digits(value))
    except ValueError:
        return fallback


def _safe_iso_date(year: int, month: int, day: int) -> Optional[str]:
    if year < 100:  # Ignore unrealistic matches like postal codes
        return None
    month = min(max(month, 1), 12)
    last_day = monthrange(year, month)[1]
    day = min(max(day, 1), last_day)
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def iter_dates(sentence: str) -> Iterable[RawEvent]:
    seen_spans: list[tuple[int, int]] = []
    for match in ERA_PATTERN.finditer(sentence):
        era_raw = match.group()
        iso_candidate = normalise_era_notation(era_raw)
        seen_spans.append(match.span())
        yield RawEvent(sentence=sentence, date_text=era_raw, date_iso=iso_candidate)

    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(sentence):
            span = match.span()
            if any(start <= span[0] and span[1] <= end for start, end in seen_spans):
                continue
            year_raw = match.group("year")
            month_raw = match.groupdict().get("month")
            day_raw = match.groupdict().get("day")
            year = _parse_number(year_raw, fallback=0)
            month = _parse_number(month_raw, fallback=1)
            day = _parse_number(day_raw, fallback=1)
            iso = _safe_iso_date(year, month, day)
            seen_spans.append(span)
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

    aggregated_events: dict[str, dict] = {}
    appearance_index: dict[str, int] = {}

    for event in unique_events:
        key = event.date_iso or event.date_text
        if key not in aggregated_events:
            appearance_index[key] = len(appearance_index)
            aggregated_events[key] = {
                "sentences": [],
                "people": OrderedDict(),
                "locations": OrderedDict(),
                "category_counts": Counter(),
                "importance": -math.inf,
                "title": "",
                "date_text": event.date_text,
                "date_iso": event.date_iso,
            }

        entry = aggregated_events[key]

        if event.sentence not in entry["sentences"]:
            entry["sentences"].append(event.sentence)

        tokens = extract_tokens(event.sentence)
        for person in detect_people(tokens):
            entry["people"].setdefault(person, None)
        for location in detect_locations(event.sentence):
            entry["locations"].setdefault(location, None)

        category = infer_category(event.sentence)
        entry["category_counts"][category] += 1

        importance = score_importance(event.sentence)
        title = build_title(event.sentence, event.date_text)

        if importance > entry["importance"]:
            entry["importance"] = importance
            entry["title"] = title
            entry["date_text"] = event.date_text
            entry["date_iso"] = event.date_iso

    sorted_entries = sorted(
        aggregated_events.items(),
        key=lambda item: (
            item[1]["date_iso"] or "9999-12-31",
            -item[1]["importance"],
            appearance_index[item[0]],
        ),
    )

    items: List[TimelineItem] = []
    for key, entry in itertools.islice(sorted_entries, 0, max_events):
        category = (
            entry["category_counts"].most_common(1)[0][0]
            if entry["category_counts"]
            else "general"
        )
        description = "\n".join(entry["sentences"])
        item = TimelineItem(
            id=str(uuid4()),
            date_text=entry["date_text"],
            date_iso=entry["date_iso"],
            title=entry["title"] or entry["date_text"],
            description=description,
            people=list(entry["people"].keys())[:5],
            locations=list(entry["locations"].keys())[:5],
            category=category,
            importance=max(0.0, round(entry["importance"], 2)),
        )
        items.append(item)

    return items
