from __future__ import annotations

import itertools
import math
import re
import sys
from calendar import monthrange
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional
from uuid import uuid4

# Add current directory to Python path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

try:
    from .text_features import (
        LOCATION_KEYWORDS,
        LOCATION_SUFFIXES,
        PEOPLE_SUFFIXES,
        CATEGORY_KEYWORDS,
    )
    from .models import TimelineItem
    from .japanese_calendar import normalise_era_notation
    from .text_cleaner import normalise_input_text
except ImportError:
    # Fallback to absolute imports when running as script
    from text_features import (
        LOCATION_KEYWORDS,
        LOCATION_SUFFIXES,
        PEOPLE_SUFFIXES,
        CATEGORY_KEYWORDS,
    )
    from models import TimelineItem
    from japanese_calendar import normalise_era_notation
    from text_cleaner import normalise_input_text

DIGIT_CLASS = "0-9０-９"

DATE_PATTERNS = [
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})年(?P<month>[{DIGIT_CLASS}]{{1,2}})月(?P<day>[{DIGIT_CLASS}]{{1,2}})日?"),
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})年(?P<month>[{DIGIT_CLASS}]{{1,2}})月"),
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})年"),
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})月(?P<day>[{DIGIT_CLASS}]{{1,2}})日"),
    re.compile(rf"(?P<year>[{DIGIT_CLASS}]{{3,4}})[-/\.](?P<month>[{DIGIT_CLASS}]{{1,2}})[-/\.](?P<day>[{DIGIT_CLASS}]{{1,2}})"),
]

ERA_PATTERN = re.compile(r"(?P<era>令和|平成|昭和|大正|明治)(?P<year>[0-9０-９]+|元)年(?:(?P<month>[0-9０-９]+)月)?(?:(?P<day>[0-9０-９]+)日)?")
RELATIVE_YEAR_PATTERN = re.compile(rf"(?P<years>[{DIGIT_CLASS}]+)年前")

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
KANJI_NAME_PATTERN = re.compile(r"^[一-龥]{2,4}$")
KATAKANA_NAME_PATTERN = re.compile(r"^[ァ-ヴー]+$")
LOCATION_COMPOUND_PATTERN = re.compile(r"[一-龥]{1,4}(?:都|道|府|県|市|区|町|村|郡|空港|駅|港|湾|半島)")
TOKEN_STRIP_CHARS = "（）()「」『』\"'、，,。:：;；!?！？〜～‐-"


@dataclass
class RawEvent:
    sentence: str
    date_text: str
    date_iso: Optional[str]
TITLE_MAX_LENGTH = 80


def split_sentences(text: str) -> List[str]:
    stripped = text.replace("\r", "")
    candidates: list[str] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        segments = [segment.strip() for segment in SENTENCE_SPLIT_PATTERN.split(line) if segment.strip()]
        if segments:
            candidates.extend(segments)
        else:
            candidates.append(line)
    if not candidates:
        candidates = [stripped.strip()]
    return candidates


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


def _relative_year_to_iso(years_text: str, reference: date) -> Optional[str]:
    years = _parse_number(years_text, fallback=-1)
    if years <= 0 or years > 3000:
        return None
    target_year = reference.year - years
    if target_year <= 0:
        return None
    return _safe_iso_date(target_year, 1, 1)


def iter_dates(sentence: str, reference: date) -> Iterable[RawEvent]:
    seen_spans: list[tuple[int, int]] = []
    for match in ERA_PATTERN.finditer(sentence):
        era_raw = match.group()
        iso_candidate = normalise_era_notation(era_raw)
        seen_spans.append(match.span())
        yield RawEvent(sentence=sentence, date_text=era_raw, date_iso=iso_candidate)

    for match in RELATIVE_YEAR_PATTERN.finditer(sentence):
        span = match.span()
        if any(start <= span[0] and span[1] <= end for start, end in seen_spans):
            continue
        iso_candidate = _relative_year_to_iso(match.group("years"), reference)
        seen_spans.append(span)
        yield RawEvent(
            sentence=sentence,
            date_text=match.group(),
            date_iso=iso_candidate,
        )

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


def _strip_token(token: str) -> str:
    return token.strip(TOKEN_STRIP_CHARS)


def _remove_person_suffix(token: str) -> str:
    for suffix in PEOPLE_SUFFIXES:
        if token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _remove_location_suffix(token: str) -> str:
    for suffix in LOCATION_SUFFIXES:
        if token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def classify_people_locations(sentence: str, tokens: List[str]) -> tuple[List[str], List[str]]:
    people_order: OrderedDict[str, None] = OrderedDict()
    locations_order: OrderedDict[str, None] = OrderedDict()
    person_bases: set[str] = set()
    location_bases: set[str] = set()

    def add_person(name: str) -> None:
        cleaned = _strip_token(name)
        if not cleaned:
            return
        base = _strip_token(_remove_person_suffix(cleaned)) or cleaned
        if base in location_bases and not any(cleaned.endswith(suf) for suf in PEOPLE_SUFFIXES):
            return
        if base not in person_bases:
            person_bases.add(base)
            people_order.setdefault(cleaned, None)

    def add_location(name: str) -> None:
        cleaned = _strip_token(name)
        if not cleaned:
            return
        base = _strip_token(_remove_location_suffix(cleaned)) or cleaned
        if base in person_bases and not any(cleaned.endswith(suf) for suf in LOCATION_SUFFIXES):
            return
        if base not in location_bases:
            location_bases.add(base)
            locations_order.setdefault(cleaned, None)

    for token in tokens:
        cleaned = _strip_token(token)
        if not cleaned:
            continue

        if cleaned in LOCATION_KEYWORDS:
            add_location(cleaned)
            continue

        if any(cleaned.endswith(suffix) for suffix in LOCATION_SUFFIXES):
            add_location(cleaned)
            continue

        base_person = _remove_person_suffix(cleaned)
        if base_person != cleaned:
            if base_person and base_person not in LOCATION_KEYWORDS and not any(base_person.endswith(suf) for suf in LOCATION_SUFFIXES):
                add_person(cleaned)
            continue

        if KANJI_NAME_PATTERN.match(cleaned) and not any(cleaned.endswith(suf) for suf in LOCATION_SUFFIXES):
            if cleaned not in LOCATION_KEYWORDS:
                add_person(cleaned)
            continue

        if "・" in cleaned:
            parts = [part for part in cleaned.split("・") if part]
            if parts and all(KANJI_NAME_PATTERN.match(part) or KATAKANA_NAME_PATTERN.match(part) for part in parts):
                add_person(cleaned)
                continue

        if KATAKANA_NAME_PATTERN.match(cleaned) and len(cleaned) >= 3:
            add_person(cleaned)
            continue

    for match in LOCATION_COMPOUND_PATTERN.finditer(sentence):
        add_location(match.group())

    for keyword in LOCATION_KEYWORDS:
        if keyword in sentence:
            add_location(keyword)

    people = list(people_order.keys())
    locations = list(locations_order.keys())

    overlap = set(people) & set(locations)
    for name in overlap:
        if any(name.endswith(suf) for suf in PEOPLE_SUFFIXES):
            if name in locations:
                locations.remove(name)
        elif any(name.endswith(suf) for suf in LOCATION_SUFFIXES):
            if name in people:
                people.remove(name)
        elif len(name) <= 2:
            if name in people:
                people.remove(name)
        else:
            if name in locations:
                locations.remove(name)

    return people[:5], locations[:5]


def infer_category(sentence: str) -> str:
    lowercase = sentence.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowercase for keyword in keywords):
            return category
    return "general"


def score_importance(sentence: str, people_count: int = 0, location_count: int = 0) -> float:
    words = re.findall(r"[\w一-龥]+", sentence.lower())
    keyword_counts = Counter(words)
    emphasis = sum(
        keyword_counts.get(keyword, 0)
        for keywords in CATEGORY_KEYWORDS.values()
        for keyword in keywords
    )
    length_bonus = min(len(sentence) / 120.0, 1.0)
    detail_bonus = min(0.25, 0.06 * min(people_count, 3) + 0.05 * min(location_count, 3))
    numeric_bonus = 0.05 if re.search(rf"[{DIGIT_CLASS}]", sentence) else 0.0
    score = min(1.0, 0.3 + 0.2 * emphasis + 0.4 * length_bonus + detail_bonus + numeric_bonus)
    return round(score, 2)


def extract_tokens(sentence: str) -> List[str]:
    return re.findall(r"[\w一-龥]+", sentence)


def build_title(sentence: str, date_text: str) -> str:
    candidate = sentence

    if sentence.startswith(date_text):
        candidate = sentence[len(date_text) :]

    candidate = candidate.lstrip("・:：、。 　")
    if not candidate:
        candidate = sentence

    clause_match = re.search(r"[。.!！？\?]", candidate)
    if clause_match:
        candidate = candidate[: clause_match.start()]
    else:
        comma_match = re.search(r"[、,，]", candidate)
        if comma_match and comma_match.start() >= 8:
            candidate = candidate[: comma_match.start()]

    candidate = candidate.strip("・:：、。 　")

    if len(candidate) > TITLE_MAX_LENGTH:
        truncated = candidate[:TITLE_MAX_LENGTH].rstrip("・:：、。 　")
        if len(truncated) < len(candidate):
            candidate = f"{truncated}…"
        else:
            candidate = truncated

    fallback = sentence[:TITLE_MAX_LENGTH].rstrip("・:：、。 　")
    return candidate or fallback


def compute_confidence(entry: dict) -> float:
    raw_importance = entry.get("importance", 0.0)
    if not isinstance(raw_importance, (int, float)) or not math.isfinite(raw_importance):
        raw_importance = 0.0
    base = min(0.8, max(0.2, 0.3 + 0.5 * raw_importance))

    iso_bonus = 0.1 if entry.get("date_iso") else 0.0

    people_container = entry.get("people") or {}
    if isinstance(people_container, (dict, OrderedDict)):
        people_count = len(people_container)
    else:
        people_count = len(list(people_container))

    locations_container = entry.get("locations") or {}
    if isinstance(locations_container, (dict, OrderedDict)):
        location_count = len(locations_container)
    else:
        location_count = len(list(locations_container))

    entity_bonus = min(0.15, 0.05 * (people_count + location_count))

    sentence_count = len(entry.get("sentences", []))
    sentence_bonus = 0.05 if sentence_count > 1 else 0.0

    category_counts = entry.get("category_counts")
    diversity_bonus = 0.05 if category_counts and len(category_counts) > 1 else 0.0

    score = min(1.0, base + iso_bonus + entity_bonus + sentence_bonus + diversity_bonus)
    return round(score, 2)


def generate_timeline(
    text: str,
    max_events: int = 150,
    reference_date: Optional[date] = None,
) -> List[TimelineItem]:
    preprocessed = normalise_input_text(text)
    sentences = split_sentences(preprocessed)
    reference = reference_date or datetime.utcnow().date()

    raw_events: List[RawEvent] = []
    for sentence in sentences:
        matches = list(iter_dates(sentence, reference))
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
        people, locations = classify_people_locations(event.sentence, tokens)
        for person in people:
            entry["people"].setdefault(person, None)
        for location in locations:
            entry["locations"].setdefault(location, None)

        category = infer_category(event.sentence)
        entry["category_counts"][category] += 1

        title = build_title(event.sentence, event.date_text)

        importance = score_importance(event.sentence, len(people), len(locations))

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
        confidence = compute_confidence(entry)
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
            confidence=confidence,
        )
        items.append(item)

    return items
