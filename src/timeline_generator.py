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
from typing import Iterable, List, Optional, Set, Tuple
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

KANJI_DIGITS = "〇零一二三四五六七八九"
KANJI_DIGIT_VALUES = {
    "〇": 0,
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
KANJI_SMALL_UNITS = {
    "十": 10,
    "百": 100,
    "千": 1000,
}
KANJI_LARGE_UNITS = {
    "万": 10_000,
    "億": 100_000_000,
    "兆": 1_000_000_000_000,
}
NUMERAL_CLASS = f"0-9０-９{KANJI_DIGITS}{''.join(KANJI_SMALL_UNITS.keys())}{''.join(KANJI_LARGE_UNITS.keys())}元"

YEAR_TOKEN = rf"(?P<year>[{NUMERAL_CLASS}]{{1,8}})"
MONTH_TOKEN = rf"(?P<month>[{NUMERAL_CLASS}]{{1,5}})"
DAY_TOKEN = rf"(?P<day>[{NUMERAL_CLASS}]{{1,5}})"

DATE_PATTERNS = [
    re.compile(rf"{YEAR_TOKEN}年{MONTH_TOKEN}月{DAY_TOKEN}日?"),
    re.compile(rf"{YEAR_TOKEN}年{MONTH_TOKEN}月"),
    re.compile(rf"{YEAR_TOKEN}年"),
    re.compile(rf"{YEAR_TOKEN}月{DAY_TOKEN}日"),
    re.compile(rf"{YEAR_TOKEN}[-/\.]" + rf"{MONTH_TOKEN}[-/\.]" + rf"{DAY_TOKEN}"),
]

ERA_NUMERAL_CLASS = f"0-9０-９{KANJI_DIGITS}{''.join(KANJI_SMALL_UNITS.keys())}"
ERA_PATTERN = re.compile(
    rf"(?P<era>令和|平成|昭和|大正|明治)(?P<year>[{ERA_NUMERAL_CLASS}]+|元)(?P<suffix>年度|年)(?:(?P<month>[{ERA_NUMERAL_CLASS}]+)月)?(?:(?P<day>[{ERA_NUMERAL_CLASS}]+)日)?"
)
RELATIVE_YEAR_PATTERN = re.compile(rf"(?P<years>[{NUMERAL_CLASS}]+)年前")
FISCAL_YEAR_PATTERN = re.compile(rf"{YEAR_TOKEN}年度")

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

TOKEN_PATTERN = re.compile(r"[\w一-龥]+")
NUMERAL_REGEX = re.compile(rf"[{NUMERAL_CLASS}]")
LOCATION_KEYWORDS_SET = set(LOCATION_KEYWORDS)
CATEGORY_KEYWORDS_LOWER = {
    category: tuple(keyword.lower() for keyword in keywords)
    for category, keywords in CATEGORY_KEYWORDS.items()
}
LEADING_SYMBOL_PATTERN = re.compile(r"^[-‐‑‒–—―－−•●◦○◆◇☆★▪▫∙·・]\s*")
FOLLOWUP_PREFIX_PATTERN = re.compile(
    r"^(同日|同年|同月|同じ日|同じ年|同夜|その日|その夜|その後|同時に)"
)
CONJUNCTION_PREFIXES: Tuple[str, ...] = tuple(
    sorted(
        (
            "しかし",
            "しかしながら",
            "だが",
            "一方",
            "その一方",
            "そのため",
            "その結果",
            "その後",
            "その上",
            "さらに",
            "また",
            "そして",
            "加えて",
            "なお",
            "ただし",
            "ところが",
            "それでも",
            "それなのに",
            "にもかかわらず",
        ),
        key=len,
        reverse=True,
    )
)


@dataclass
class RawEvent:
    sentence: str
    date_text: str
    date_iso: Optional[str]
    relative_years: Optional[int] = None
    reference_year: Optional[int] = None
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


def _is_followup_sentence(sentence: str) -> bool:
    stripped = sentence.strip()
    if not stripped:
        return False
    return bool(FOLLOWUP_PREFIX_PATTERN.match(stripped))


def _strip_leading_conjunctions(text: str) -> str:
    candidate = text.lstrip()
    while candidate:
        for prefix in CONJUNCTION_PREFIXES:
            if candidate.startswith(prefix):
                remainder = candidate[len(prefix) :].lstrip("、,，・:： 　")
                if remainder == candidate:
                    return candidate
                candidate = remainder.lstrip()
                break
        else:
            break
    return candidate


def _normalise_digits(value: str) -> str:
    return value.translate(FULLWIDTH_DIGIT_TABLE)


def _convert_japanese_numerals_to_int(raw: str) -> Optional[int]:
    if raw is None:
        return None
    cleaned = re.sub(r"[\s　,，_]", "", raw)
    if not cleaned:
        return None
    cleaned = _normalise_digits(cleaned)
    if not cleaned:
        return None
    if cleaned == "元":
        return 1

    if all(ch in KANJI_DIGIT_VALUES for ch in cleaned):
        digits = "".join(str(KANJI_DIGIT_VALUES[ch]) for ch in cleaned)
        return int(digits)

    total = 0
    section = 0
    current_digit = None

    for ch in cleaned:
        if ch in KANJI_DIGIT_VALUES:
            current_digit = KANJI_DIGIT_VALUES[ch]
            continue

        if ch.isdigit():
            current_digit = int(ch)
            continue

        if ch in KANJI_SMALL_UNITS:
            multiplier = KANJI_SMALL_UNITS[ch]
            value = current_digit if current_digit is not None else 1
            section += value * multiplier
            current_digit = None
            continue

        if ch in KANJI_LARGE_UNITS:
            unit_value = KANJI_LARGE_UNITS[ch]
            if current_digit is not None:
                section += current_digit
            if section == 0:
                section = 1
            total += section * unit_value
            section = 0
            current_digit = None
            continue

        return None

    if current_digit is not None:
        section += current_digit

    result = total + section
    return result if result != 0 else None


def _parse_number(value: Optional[str], fallback: int = 1) -> int:
    if value is None:
        return fallback
    candidate = _normalise_digits(value).strip()
    candidate = re.sub(r"[,_，]", "", candidate)
    if not candidate:
        return fallback
    if re.fullmatch(r"[0-9]+", candidate):
        try:
            return int(candidate)
        except ValueError:
            return fallback

    kanji_value = _convert_japanese_numerals_to_int(value)
    if kanji_value is not None:
        return kanji_value

    kanji_value = _convert_japanese_numerals_to_int(candidate)
    if kanji_value is not None:
        return kanji_value

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


def _relative_year_to_iso(years_text: str, reference: date) -> tuple[Optional[str], Optional[int]]:
    years = _parse_number(years_text, fallback=-1)
    if years <= 0:
        return None, None

    target_year = reference.year - years
    iso_candidate = None
    if target_year > 0:
        iso_candidate = _safe_iso_date(target_year, 1, 1)
    return iso_candidate, years


def iter_dates(sentence: str, reference: date) -> Iterable[RawEvent]:
    seen_spans: list[tuple[int, int]] = []
    for match in ERA_PATTERN.finditer(sentence):
        era_raw = match.group()
        iso_candidate = normalise_era_notation(era_raw)
        seen_spans.append(match.span())
        yield RawEvent(
            sentence=sentence,
            date_text=era_raw,
            date_iso=iso_candidate,
            reference_year=reference.year,
        )

    for match in RELATIVE_YEAR_PATTERN.finditer(sentence):
        span = match.span()
        if any(start <= span[0] and span[1] <= end for start, end in seen_spans):
            continue
        iso_candidate, relative_years = _relative_year_to_iso(match.group("years"), reference)
        seen_spans.append(span)
        yield RawEvent(
            sentence=sentence,
            date_text=match.group(),
            date_iso=iso_candidate,
            relative_years=relative_years,
            reference_year=reference.year,
        )

    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(sentence):
            span = match.span()
            if any(start <= span[0] and span[1] <= end for start, end in seen_spans):
                continue
            if sentence[span[1]: span[1] + 1] == "度":
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
                reference_year=reference.year,
            )

    for match in FISCAL_YEAR_PATTERN.finditer(sentence):
        span = match.span()
        if any(start <= span[0] and span[1] <= end for start, end in seen_spans):
            continue
        year_raw = match.group("year")
        year = _parse_number(year_raw, fallback=0)
        if year <= 0:
            continue
        iso = _safe_iso_date(year, 4, 1)
        seen_spans.append(span)
        yield RawEvent(
            sentence=sentence,
            date_text=match.group(),
            date_iso=iso,
            reference_year=reference.year,
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

        if cleaned in LOCATION_KEYWORDS_SET:
            add_location(cleaned)
            continue

        if any(cleaned.endswith(suffix) for suffix in LOCATION_SUFFIXES):
            add_location(cleaned)
            continue

        base_person = _remove_person_suffix(cleaned)
        if base_person != cleaned:
            if base_person and base_person not in LOCATION_KEYWORDS_SET and not any(base_person.endswith(suf) for suf in LOCATION_SUFFIXES):
                add_person(cleaned)
            continue

        if KANJI_NAME_PATTERN.match(cleaned) and not any(cleaned.endswith(suf) for suf in LOCATION_SUFFIXES):
            if cleaned not in LOCATION_KEYWORDS_SET:
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


def infer_category(sentence: str, lower_sentence: Optional[str] = None) -> str:
    lowercase = lower_sentence if lower_sentence is not None else sentence.lower()
    for category, keywords in CATEGORY_KEYWORDS_LOWER.items():
        if any(keyword in lowercase for keyword in keywords):
            return category
    return "general"


def score_importance(
    sentence: str,
    people_count: int = 0,
    location_count: int = 0,
    *,
    tokens: Optional[List[str]] = None,
    has_numeral: Optional[bool] = None,
) -> float:
    token_iterable = tokens if tokens is not None else TOKEN_PATTERN.findall(sentence)
    words = [token.lower() for token in token_iterable]
    keyword_counts = Counter(words)
    emphasis = sum(
        keyword_counts.get(keyword, 0)
        for keywords in CATEGORY_KEYWORDS_LOWER.values()
        for keyword in keywords
    )
    length_bonus = min(len(sentence) / 120.0, 1.0)
    detail_bonus = min(0.25, 0.06 * min(people_count, 3) + 0.05 * min(location_count, 3))
    numeric_bonus = 0.05 if (has_numeral if has_numeral is not None else bool(NUMERAL_REGEX.search(sentence))) else 0.0
    score = min(1.0, 0.3 + 0.2 * emphasis + 0.4 * length_bonus + detail_bonus + numeric_bonus)
    return round(score, 2)


def extract_tokens(sentence: str) -> List[str]:
    return TOKEN_PATTERN.findall(sentence)


def build_title(sentence: str, date_text: str) -> str:
    candidate = sentence

    if sentence.startswith(date_text):
        candidate = sentence[len(date_text) :]

    candidate = candidate.lstrip("・:：、。 　")
    candidate = _strip_leading_conjunctions(candidate)
    if not candidate:
        candidate = sentence

    candidate = _strip_parenthetical_dates(candidate)

    clause_match = re.search(r"[。.!！？\?]", candidate)
    if clause_match:
        candidate = candidate[: clause_match.start()]
    else:
        comma_match = re.search(r"[、,，]", candidate)
        if comma_match and comma_match.start() >= 8:
            candidate = candidate[: comma_match.start()]

    candidate = candidate.strip("・:：、。 　")
    candidate = _strip_leading_conjunctions(candidate)
    candidate = _strip_parenthetical_dates(candidate)

    while True:
        stripped = LEADING_SYMBOL_PATTERN.sub("", candidate, count=1)
        if stripped == candidate:
            break
        candidate = stripped.lstrip()

    if not candidate or _MEANINGLESS_PATTERN.match(candidate):
        alt = _first_meaningful_clause(sentence, date_text)
        if alt:
            candidate = alt

    if not candidate or _MEANINGLESS_PATTERN.match(candidate):
        fallback = sentence[:TITLE_MAX_LENGTH].rstrip("・:：、。 　")
        fallback = _strip_leading_conjunctions(fallback)
        return fallback

    if len(candidate) > TITLE_MAX_LENGTH:
        truncated = candidate[:TITLE_MAX_LENGTH].rstrip("・:：、。 　")
        if len(truncated) < len(candidate):
            candidate = f"{truncated}…"
        else:
            candidate = truncated

    return candidate


def _update_entry_with_sentence(
    entry: dict,
    sentence: str,
    *,
    tokens: List[str],
    lower_sentence: str,
    has_numeral: bool,
    allow_title_update: bool,
    event_date_text: Optional[str] = None,
    event_date_iso: Optional[str] = None,
) -> None:
    if sentence not in entry["sentences"]:
        entry["sentences"].append(sentence)

    people, locations = classify_people_locations(sentence, tokens)
    for person in people:
        entry["people"].setdefault(person, None)
    for location in locations:
        entry["locations"].setdefault(location, None)

    category = infer_category(sentence, lower_sentence=lower_sentence)
    entry["category_counts"][category] += 1

    importance = score_importance(
        sentence,
        len(people),
        len(locations),
        tokens=tokens,
        has_numeral=has_numeral,
    )

    if allow_title_update and importance > entry["importance"]:
        reference_date_text = event_date_text or entry["date_text"]
        entry["importance"] = importance
        entry["title"] = build_title(sentence, reference_date_text)
        if event_date_text:
            entry["date_text"] = event_date_text
        if event_date_iso is not None:
            entry["date_iso"] = event_date_iso
    else:
        entry["importance"] = max(entry["importance"], importance)
_MEANINGLESS_PATTERN = re.compile(rf"^[\s{NUMERAL_CLASS}年月日・:：、。　/-]+$")

ERA_NAMES = ("令和", "平成", "昭和", "大正", "明治")
FUZZY_SUFFIX_PATTERN = re.compile(r"(頃|ごろ|前半|後半|上旬|中旬|下旬|初頭|末|末頃|ごろには|頃には|ごろまで|頃まで)$")


def _is_parenthetical_date(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    for era in ERA_NAMES:
        cleaned = cleaned.replace(era, "")
    cleaned = re.sub(rf"[{NUMERAL_CLASS}元年月日／/・\.\-\s　]", "", cleaned)
    return cleaned == ""


def _strip_parenthetical_dates(text: str) -> str:
    result = text
    while True:
        match = re.match(r"^[（(][^（）()]{0,40}[）)]", result)
        if not match:
            break
        inner = match.group()[1:-1]
        if _is_parenthetical_date(inner):
            result = result[match.end():].lstrip("・:：、。 　")
        else:
            break

    while True:
        match = re.search(r"[（(][^（）()]{0,40}[）)]\s*$", result)
        if not match:
            break
        inner = result[match.start() + 1 : match.end() - 1]
        if _is_parenthetical_date(inner):
            result = result[: match.start()].rstrip("・:：、。 　")
        else:
            break

    return result


def has_meaningful_content(sentence: str, date_text: str) -> bool:
    remainder = sentence
    if date_text:
        remainder = remainder.replace(date_text, " ", 1)
    remainder = remainder.strip()
    remainder = remainder.strip("・:：、。 　")
    remainder = _strip_leading_conjunctions(remainder)
    if not remainder:
        return False
    if _MEANINGLESS_PATTERN.match(remainder):
        return False
    return bool(re.search(r"[A-Za-z一-龥ぁ-んァ-ヴー]", remainder))


def _first_meaningful_clause(sentence: str, date_text: str) -> Optional[str]:
    for part in re.split(r"[。.!！？\?,、,，]", sentence):
        candidate = part.strip("・:：、。 　")
        if not candidate:
            continue
        candidate = _strip_leading_conjunctions(candidate)
        if not candidate:
            continue
        if has_meaningful_content(candidate, ""):
            return candidate
    if has_meaningful_content(sentence, date_text):
        stripped = sentence.strip("・:：、。 　")
        stripped = _strip_leading_conjunctions(stripped)
        if stripped:
            return stripped
    return None


def _strip_fuzzy_suffixes(text: str) -> str:
    result = text
    while True:
        updated = FUZZY_SUFFIX_PATTERN.sub("", result).strip()
        if updated == result:
            break
        result = updated
    return result


def _parse_sort_candidate(
    date_iso: Optional[str],
    date_text: str,
    *,
    relative_years: Optional[int] = None,
    reference_year: Optional[int] = None,
) -> Optional[tuple[int, int, int, int]]:
    if date_iso:
        try:
            year, month, day = (int(part) for part in date_iso.split("-"))
            return (year, month, day, 0)
        except ValueError:
            pass

    if relative_years is not None:
        base_year = reference_year if reference_year is not None else datetime.utcnow().year
        approx_year = base_year - relative_years
        return (approx_year, 1, 1, 2)

    cleaned = _strip_fuzzy_suffixes(date_text)
    cleaned = cleaned.strip("・:：、。 　")
    if not cleaned:
        return None

    # Try to normalise era notations
    era_iso = normalise_era_notation(cleaned)
    if era_iso:
        try:
            year, month, day = (int(part) for part in era_iso.split("-"))
            return (year, month, day, 0)
        except ValueError:
            pass

    for pattern in DATE_PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue
        groups = match.groupdict()
        year_raw = groups.get("year")
        month_raw = groups.get("month")
        day_raw = groups.get("day")
        if not year_raw:
            continue
        year = _parse_number(year_raw, fallback=0)
        month = _parse_number(month_raw, fallback=1) if month_raw else 1
        day = _parse_number(day_raw, fallback=1) if day_raw else 1

        if year <= 0:
            continue

        precision = 2
        if month_raw:
            precision = 1
        if day_raw:
            precision = 0

        month = min(max(month, 1), 12)
        day = min(max(day, 1), 31)
        return (year, month, day, precision)

    return None


def _choose_sort_key(entry: dict, candidate: Optional[tuple[int, int, int, int]]) -> None:
    if candidate is None:
        return
    existing = entry.get("sort_key")
    if existing is None:
        entry["sort_key"] = candidate
        return
    if (candidate[0], candidate[1], candidate[2]) < (existing[0], existing[1], existing[2]):
        entry["sort_key"] = candidate
        return
    if (candidate[0], candidate[1], candidate[2]) == (existing[0], existing[1], existing[2]) and candidate[3] < existing[3]:
        entry["sort_key"] = candidate


def _timeline_sort_key(entry: dict, appearance_order: int) -> tuple:
    sort_tuple = entry.get("sort_key")
    if sort_tuple:
        year, month, day, precision = sort_tuple
        return (0, year, month, day, precision, -entry["importance"], appearance_order)
    fallback_date = entry.get("date_iso")
    if fallback_date:
        try:
            year, month, day = (int(part) for part in fallback_date.split("-"))
            return (0, year, month, day, 0, -entry["importance"], appearance_order)
        except ValueError:
            pass
    return (1, appearance_order)


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

    aggregated_events: dict[str, dict] = {}
    appearance_index: dict[str, int] = {}
    token_cache: dict[str, List[str]] = {}
    lowercase_cache: dict[str, str] = {}
    numeral_cache: dict[str, bool] = {}
    seen_pairs: Set[Tuple[str, str]] = set()
    last_event_key: Optional[str] = None

    def _lower(sentence: str) -> str:
        lowered = lowercase_cache.get(sentence)
        if lowered is None:
            lowered = sentence.lower()
            lowercase_cache[sentence] = lowered
        return lowered

    def _tokens(sentence: str) -> List[str]:
        cached = token_cache.get(sentence)
        if cached is None:
            cached = extract_tokens(sentence)
            token_cache[sentence] = cached
        return cached

    def _has_numeral(sentence: str) -> bool:
        result = numeral_cache.get(sentence)
        if result is None:
            result = bool(NUMERAL_REGEX.search(sentence))
            numeral_cache[sentence] = result
        return result

    for sentence in sentences:
        stripped = sentence.strip()
        if not stripped:
            continue

        matches = list(iter_dates(sentence, reference))
        if matches:
            for event in matches:
                pair = (sentence, event.date_text)
                if pair in seen_pairs:
                    continue
                if not has_meaningful_content(sentence, event.date_text):
                    continue

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
                        "sort_key": None,
                    }

                entry = aggregated_events[key]

                sort_candidate = _parse_sort_candidate(
                    event.date_iso,
                    event.date_text,
                    relative_years=event.relative_years,
                    reference_year=event.reference_year,
                )
                _choose_sort_key(entry, sort_candidate)

                lowercase_sentence = _lower(sentence)
                tokens = _tokens(sentence)
                has_numeral = _has_numeral(sentence)

                _update_entry_with_sentence(
                    entry,
                    sentence,
                    tokens=tokens,
                    lower_sentence=lowercase_sentence,
                    has_numeral=has_numeral,
                    allow_title_update=True,
                    event_date_text=event.date_text,
                    event_date_iso=event.date_iso,
                )

                seen_pairs.add(pair)
                last_event_key = key
            continue

        if last_event_key and _is_followup_sentence(sentence):
            entry = aggregated_events.get(last_event_key)
            if entry is None:
                continue
            if not has_meaningful_content(sentence, entry["date_text"]):
                continue

            lowercase_sentence = _lower(sentence)
            tokens = _tokens(sentence)
            has_numeral = _has_numeral(sentence)

            _update_entry_with_sentence(
                entry,
                sentence,
                tokens=tokens,
                lower_sentence=lowercase_sentence,
                has_numeral=has_numeral,
                allow_title_update=False,
            )
            continue

    sorted_entries = sorted(
        aggregated_events.items(),
        key=lambda item: _timeline_sort_key(item[1], appearance_index[item[0]]),
    )

    items: List[TimelineItem] = []
    for key, entry in itertools.islice(sorted_entries, 0, max_events):
        if not entry["sentences"]:
            continue
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
