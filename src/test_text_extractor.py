from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

from . import text_extractor
from .text_extractor import MAX_CHARACTERS, MAX_FILE_SIZE, extract_text_from_upload


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_extract_text_truncates_large_text():
    content = ("あ" * (MAX_CHARACTERS + 100)).encode("utf-8")
    upload = UploadFile(filename="large.txt", file=io.BytesIO(content))

    text, preview = await extract_text_from_upload(upload)

    assert len(text) == MAX_CHARACTERS
    assert len(preview) <= 200


@pytest.mark.anyio
async def test_extract_text_rejects_oversized_file():
    content = b"a" * (MAX_FILE_SIZE + 1)
    upload = UploadFile(filename="oversize.txt", file=io.BytesIO(content))

    with pytest.raises(HTTPException) as exc_info:
        await extract_text_from_upload(upload)

    assert exc_info.value.status_code == 413


@pytest.mark.anyio
async def test_extract_text_rejects_empty_text():
    upload = UploadFile(filename="empty.txt", file=io.BytesIO(b""))

    with pytest.raises(HTTPException) as exc_info:
        await extract_text_from_upload(upload)

    assert exc_info.value.status_code == 400
    assert "テキスト" in exc_info.value.detail


@pytest.mark.anyio
async def test_extract_text_uses_ocr_for_image(monkeypatch):
    upload = UploadFile(filename="sample.png", file=io.BytesIO(b"fake-binary"))

    monkeypatch.setattr(text_extractor, "has_ocr", lambda: True)
    monkeypatch.setattr(
        text_extractor,
        "extract_text_from_image",
        lambda data, lang="jpn": "OCR結果 テキスト",
    )

    text, preview = await extract_text_from_upload(upload)

    assert text == "OCR結果 テキスト"
    assert preview.startswith("OCR結果")


@pytest.mark.anyio
async def test_extract_text_rejects_image_when_ocr_missing(monkeypatch):
    upload = UploadFile(filename="sample.png", file=io.BytesIO(b"fake-binary"))

    monkeypatch.setattr(text_extractor, "has_ocr", lambda: False)

    with pytest.raises(HTTPException) as exc_info:
        await extract_text_from_upload(upload)

    assert exc_info.value.status_code == 503
