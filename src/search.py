from __future__ import annotations

from datetime import date, datetime
from typing import List, Sequence

from .models import SearchResult, TimelineItem

FIELD_WEIGHTS = {
    "title": 3.0,
    "description": 2.0,
    "people": 1.5,
    "locations": 1.5,
    "category": 1.0,
    "date": 0.5,
}


def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:  # pragma: no cover - validation guarded earlier
        return None


def _apply_keyword(item: TimelineItem, keyword_lower: str, matched_fields: set[str]) -> bool:
    matched = False
    title = item.title.casefold()
    if keyword_lower in title:
        matched_fields.add("title")
        matched = True

    description = item.description.casefold()
    if keyword_lower in description:
        matched_fields.add("description")
        matched = True

    for person in item.people:
        if keyword_lower in person.casefold():
            matched_fields.add("people")
            matched = True
            break

    for location in item.locations:
        if keyword_lower in location.casefold():
            matched_fields.add("locations")
            matched = True
            break

    if keyword_lower in item.category.casefold():
        matched_fields.add("category")
        matched = True

    if keyword_lower in item.date_text.casefold():
        matched_fields.add("date")
        matched = True

    return matched


def search_timeline_items(
    items: Sequence[TimelineItem],
    *,
    keywords: Sequence[str],
    categories: Sequence[str],
    date_from: date | None,
    date_to: date | None,
    match_mode: str,
    max_results: int,
) -> List[SearchResult]:
    """Filter and rank timeline items based on search criteria."""

    normalised_keywords = [(keyword, keyword.casefold()) for keyword in keywords]
    category_filters = {category.lower() for category in categories if category}
    wants_all_keywords = match_mode == "all" and normalised_keywords

    results: List[SearchResult] = []

    for item in items:
        matched_fields: set[str] = set()

        if category_filters and item.category.lower() not in category_filters:
            continue
        if category_filters:
            matched_fields.add("category")

        if date_from or date_to:
            if not item.date_iso:
                continue
            iso_date = _parse_iso_date(item.date_iso)
            if iso_date is None:
                continue
            if date_from and iso_date < date_from:
                continue
            if date_to and iso_date > date_to:
                continue
            matched_fields.add("date")

        matched_keywords: List[str] = []
        if normalised_keywords:
            for original, lowered in normalised_keywords:
                if _apply_keyword(item, lowered, matched_fields):
                    matched_keywords.append(original)

            if not matched_keywords:
                continue
            if wants_all_keywords and len(matched_keywords) < len(normalised_keywords):
                continue

        score = float(item.importance)
        for field in matched_fields:
            score += FIELD_WEIGHTS.get(field, 0.0)
        if matched_keywords:
            score += 0.3 * len(matched_keywords)

        result = SearchResult(
            item=item,
            score=round(score, 3),
            matched_keywords=list(dict.fromkeys(matched_keywords)),
            matched_fields=sorted(matched_fields),
        )
        results.append(result)

    results.sort(
        key=lambda result: (
            result.score,
            result.item.importance,
            result.item.date_iso or "",
        ),
        reverse=True,
    )

    if len(results) > max_results:
        results = results[:max_results]

    return results


__all__ = ["search_timeline_items"]
