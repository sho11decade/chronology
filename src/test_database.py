from __future__ import annotations

from datetime import datetime

from .database import fetch_recent_timelines, fetch_timeline, init_db, store_timeline
from .models import TimelineItem


def _create_sample_items() -> list[TimelineItem]:
    return [
        TimelineItem(
            date_text="2020年1月1日",
            date_iso="2020-01-01",
            title="新年の行事",
            description="2020年1月1日、東京で新年の行事が開催された。",
            people=["関係者"],
            locations=["東京"],
            category="culture",
            importance=0.8,
        )
    ]


def test_database_store_and_fetch(tmp_path):
    db_path = tmp_path / "chronology.db"
    init_db(db_path=db_path)

    items = _create_sample_items()
    request_id = store_timeline("サンプルテキスト", items, db_path=db_path)

    recent = fetch_recent_timelines(limit=5, db_path=db_path)
    assert recent
    assert recent[0][0] == request_id
    assert recent[0][2] == len(items)

    generated_at, stored_items = fetch_timeline(request_id, db_path=db_path)
    assert generated_at is not None
    assert stored_items
    stored_item = stored_items[0]
    assert stored_item.title == items[0].title
    assert stored_item.people == items[0].people
    assert stored_item.locations == items[0].locations


def test_database_missing_request(tmp_path):
    db_path = tmp_path / "chronology.db"
    init_db(db_path=db_path)
    generated_at, items = fetch_timeline(999, db_path=db_path)
    assert generated_at is None
    assert items == []


def test_fetch_recent_timelines_limit(tmp_path):
    db_path = tmp_path / "chronology.db"
    init_db(db_path=db_path)

    for index in range(3):
        items = _create_sample_items()
        items[0].title = f"イベント{index}"
        store_timeline(f"テキスト{index}", items, db_path=db_path)

    recent = fetch_recent_timelines(limit=2, db_path=db_path)
    assert len(recent) == 2
    assert isinstance(recent[0][0], int)
    assert isinstance(recent[0][1], datetime)
    assert recent[0][2] == 1