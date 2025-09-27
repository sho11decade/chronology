from __future__ import annotations

import re
from datetime import date
from typing import Optional

ERA_OFFSETS = {
    "令和": 2018,
    "平成": 1988,
    "昭和": 1925,
    "大正": 1911,
    "明治": 1867,
}

FULLWIDTH_DIGIT_PATTERN = str.maketrans({
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

NUMERAL_CLASS = "0-9０-９〇零一二三四五六七八九十百千元"

ERA_REGEX = re.compile(
    rf"(?P<era>令和|平成|昭和|大正|明治)(?P<year>[{NUMERAL_CLASS}]+|元)年(?:(?P<month>[{NUMERAL_CLASS}]+)月)?(?:(?P<day>[{NUMERAL_CLASS}]+)日)?"
)


def _convert_kanji_numeral_to_int(text: str) -> Optional[int]:
    cleaned = text.strip()
    if not cleaned:
        return None
    cleaned = cleaned.translate(FULLWIDTH_DIGIT_PATTERN)
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
        return None

    if current_digit is not None:
        section += current_digit

    return total + section if (total + section) != 0 else None


def _normalise_number(text: Optional[str], default: int) -> int:
    if text is None or text == "":
        return default
    if text == "元":
        return 1
    candidate = text.translate(FULLWIDTH_DIGIT_PATTERN)
    candidate = candidate.replace(",", "").replace("，", "")
    if candidate.isdigit():
        return int(candidate)
    kanji_value = _convert_kanji_numeral_to_int(text)
    if kanji_value is not None:
        return kanji_value
    return default


def normalise_era_notation(text: str) -> Optional[str]:
    match = ERA_REGEX.search(text)
    if not match:
        return None

    era = match.group("era")
    raw_year = match.group("year")
    raw_month = match.group("month") or "1"
    raw_day = match.group("day") or "1"

    year_num = _normalise_number(raw_year, 1)
    month_num = _normalise_number(raw_month, 1)
    day_num = _normalise_number(raw_day, 1)

    offset = ERA_OFFSETS.get(era)
    if offset is None:
        return None

    # Safeguards for invalid calendar dates
    month_num = min(max(month_num, 1), 12)
    day_num = min(max(day_num, 1), 28)

    gregorian_year = offset + year_num
    try:
        iso_value = date(gregorian_year, month_num, day_num).isoformat()
    except ValueError:
        iso_value = date(gregorian_year, month_num, 1).isoformat()
    return iso_value
