from __future__ import annotations

import io

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

try:  # pragma: no cover - 環境によっては OCR 依存が未導入
    import pytesseract  # type: ignore[import]
except ImportError:  # pragma: no cover - OCR を使わずに続行
    pytesseract = None  # type: ignore[assignment]


_OCR_INITIALISED = False
_OCR_AVAILABLE = False


def has_ocr() -> bool:
    """pytesseract / Tesseract の利用可否をキャッシュしながら判定する。"""
    global _OCR_INITIALISED, _OCR_AVAILABLE
    if _OCR_INITIALISED:
        return _OCR_AVAILABLE
    _OCR_INITIALISED = True
    if pytesseract is None:
        _OCR_AVAILABLE = False
        return False
    try:
        pytesseract.get_tesseract_version()
    except Exception:  # pragma: no cover - バイナリ未導入時
        _OCR_AVAILABLE = False
        return False
    _OCR_AVAILABLE = True
    return True


def extract_text_from_image(image_bytes: bytes, *, lang: str = "jpn") -> str:
    """画像バイト列から OCR テキストを抽出する。"""
    if pytesseract is None or not has_ocr():
        raise RuntimeError("OCR runtime is not available.")

    image = _load_image(image_bytes)
    processed = _preprocess_image(image)

    try:
        text = pytesseract.image_to_string(processed, lang=lang)  # type: ignore[call-arg]
    except Exception:  # pragma: no cover - lang 未導入など
        if lang != "eng":
            text = pytesseract.image_to_string(processed, lang="eng")  # type: ignore[call-arg]
        else:
            raise
    finally:
        image.close()
        processed.close()

    return text.strip()


def _load_image(image_bytes: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        raise ValueError("画像を読み込めませんでした。") from exc


def _preprocess_image(image: Image.Image) -> Image.Image:
    grayscale = image.convert("L")
    contrasted = ImageOps.autocontrast(grayscale)
    denoised = contrasted.filter(ImageFilter.MedianFilter(size=3))

    def _threshold(value: int) -> int:
        return 255 if value > 140 else 0

    binary = denoised.point(_threshold)
    return binary.convert("L")
