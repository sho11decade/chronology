from __future__ import annotations

import io
from typing import Tuple

from starlette.status import HTTP_413_REQUEST_ENTITY_TOO_LARGE

from fastapi import HTTPException, UploadFile

from .ocr_extractor import extract_text_from_image, has_ocr

TEXT_EXTENSIONS = {".txt"}
DOCUMENT_EXTENSIONS = {".docx", ".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
MAX_CHARACTERS = 200_000
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
READ_CHUNK_SIZE = 1 * 1024 * 1024  # 1 MB


async def extract_text_from_upload(
    upload: UploadFile,
    *,
    max_characters: int = MAX_CHARACTERS,
    ocr_lang: str = "jpn",
) -> Tuple[str, str]:
    filename = upload.filename or "uploaded"
    extension = _infer_extension(filename)

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="対応していないファイル形式です。")

    try:
        if extension in TEXT_EXTENSIONS:
            text = await _read_txt(upload)
        elif extension in DOCUMENT_EXTENSIONS:
            if extension == ".docx":
                text = await _read_docx(upload)
            else:
                text = await _read_pdf(upload)
        else:
            text = await _read_image(upload, lang=ocr_lang)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=400, detail="ファイルの解析中にエラーが発生しました。") from exc

    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="ファイルからテキストを抽出できませんでした。")
    if len(text) > max_characters:
        text = text[:max_characters]

    preview = text[:200].replace("\n", " ")
    return text, preview


def _infer_extension(filename: str) -> str:
    lowered = filename.lower()
    for extension in SUPPORTED_EXTENSIONS:
        if lowered.endswith(extension):
            return extension
    return ""


async def _read_txt(upload: UploadFile) -> str:
    data = await _read_bytes(upload)
    return data.decode("utf-8", errors="ignore")


async def _read_docx(upload: UploadFile) -> str:
    from docx import Document  # type: ignore

    data = await _read_bytes(upload)
    document = Document(io.BytesIO(data))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs)


async def _read_pdf(upload: UploadFile) -> str:
    import pdfplumber  # type: ignore

    data = await _read_bytes(upload)
    buffer = io.BytesIO(data)
    text_chunks = []
    with pdfplumber.open(buffer) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            text_chunks.append(text)
    return "\n".join(text_chunks)


async def _read_image(upload: UploadFile, *, lang: str) -> str:
    data = await _read_bytes(upload)

    if not has_ocr():
        raise HTTPException(status_code=503, detail="OCR機能が利用できません。管理者に問い合わせてください。")

    try:
        text = extract_text_from_image(data, lang=lang)
    except RuntimeError as exc:  # OCR バイナリ未導入
        raise HTTPException(status_code=503, detail="OCRエンジンが初期化されていません。Tesseract をセットアップしてください。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - 予期せぬ例外
        raise HTTPException(status_code=400, detail="画像からテキストを抽出できませんでした。") from exc

    return text


async def _read_bytes(upload: UploadFile, *, limit: int = MAX_FILE_SIZE) -> bytes:
    await upload.seek(0)
    buffer = bytearray()
    while True:
        chunk = await upload.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise HTTPException(
                status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="ファイルサイズが大きすぎます。最大5MBまで対応しています。",
            )
    await upload.seek(0)
    return bytes(buffer)
