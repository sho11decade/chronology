from __future__ import annotations

import io
from typing import Tuple

from fastapi import HTTPException, UploadFile

SUPPORTED_EXTENSIONS = {".txt", ".docx", ".pdf"}
MAX_CHARACTERS = 50_000


async def extract_text_from_upload(upload: UploadFile) -> Tuple[str, str]:
    filename = upload.filename or "uploaded"
    extension = _infer_extension(filename)

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="対応していないファイル形式です。")

    if extension == ".txt":
        raw_bytes = await upload.read()
        text = raw_bytes.decode("utf-8", errors="ignore")
    elif extension == ".docx":
        text = await _read_docx(upload)
    else:  # .pdf
        text = await _read_pdf(upload)

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="ファイルからテキストを抽出できませんでした。")
    if len(text) > MAX_CHARACTERS:
        text = text[:MAX_CHARACTERS]

    preview = text[:200].replace("\n", " ")
    return text, preview


def _infer_extension(filename: str) -> str:
    lowered = filename.lower()
    for extension in SUPPORTED_EXTENSIONS:
        if lowered.endswith(extension):
            return extension
    return ""


async def _read_docx(upload: UploadFile) -> str:
    from docx import Document  # type: ignore

    data = await upload.read()
    document = Document(io.BytesIO(data))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs)


async def _read_pdf(upload: UploadFile) -> str:
    import pdfplumber  # type: ignore

    data = await upload.read()
    buffer = io.BytesIO(data)
    text_chunks = []
    with pdfplumber.open(buffer) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            text_chunks.append(text)
    return "\n".join(text_chunks)
