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

ERA_REGEX = re.compile(
    r"(?P<era>令和|平成|昭和|大正|明治)(?P<year>[0-9０-９]+|元)年(?:" r"(?P<month>[0-9０-９]+)月)?(?:" r"(?P<day>[0-9０-９]+)日)?"
)


def normalise_era_notation(text: str) -> Optional[str]:
    match = ERA_REGEX.search(text)
    if not match:
        return None

    era = match.group("era")
    raw_year = match.group("year")
    raw_month = match.group("month") or "1"
    raw_day = match.group("day") or "1"

    if raw_year == "元":
        year_num = 1
    else:
        year_num = int(raw_year.translate(FULLWIDTH_DIGIT_PATTERN))

    month_num = int(raw_month.translate(FULLWIDTH_DIGIT_PATTERN))
    day_num = int(raw_day.translate(FULLWIDTH_DIGIT_PATTERN))

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
