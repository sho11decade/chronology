from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, validator


class TimelineItem(BaseModel):
    """Represents a single entry inside the generated chronology."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    date_text: str = Field(..., description="Readable representation of the detected date")
    date_iso: Optional[str] = Field(
        default=None,
        description="ISO-8601 formatted date string when the date could be normalised.",
    )
    title: str = Field(..., description="Short headline describing the event")
    description: str = Field(..., description="Longer summary extracted from the source text")
    people: List[str] = Field(default_factory=list, description="People associated with the event")
    locations: List[str] = Field(default_factory=list, description="Locations related to the event")
    category: str = Field(default="general", description="High-level category of the event")
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Normalised importance score between 0 and 1",
    )

    @validator("category")
    def normalise_category(cls, value: str) -> str:
        return value.lower()

    @validator("date_iso")
    def validate_iso(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        # Ensure ISO strings are valid
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise ValueError("date_iso must be an ISO-8601 formatted string") from exc
        return value


class GenerateRequest(BaseModel):
    text: str = Field(
        ...,
        max_length=50000,
        description="Input text from which the timeline should be generated",
    )

    @validator("text")
    def ensure_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("テキストが空です。内容を入力してください。")
        return cleaned


class GenerateResponse(BaseModel):
    items: List[TimelineItem]
    total_events: int
    generated_at: datetime


class UploadResponse(BaseModel):
    filename: str
    characters: int
    text_preview: str
    text: str
