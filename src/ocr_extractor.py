from __future__ import annotations

import io
import re
from typing import List

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

try:  # pragma: no cover - 環境によっては OCR 依存が未導入
    import pytesseract  # type: ignore[import]
except ImportError:  # pragma: no cover - OCR を使わずに続行
    pytesseract = None  # type: ignore[assignment]


DEFAULT_TESSERACT_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
VERTICAL_TESSERACT_CONFIG = "--oem 3 --psm 5 -c preserve_interword_spaces=1"
_JAPANESE_CHAR_PATTERN = re.compile(r"[一-龥ぁ-んァ-ヴー々〆ヶー]")


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
        rotation_hint = 0
        osd_image = processed.copy()
        try:
            rotation_hint = _detect_rotation(osd_image)
        finally:
            osd_image.close()

        best_text = ""
        best_score = float("-inf")

        for angle in _generate_candidate_angles(rotation_hint):
            if angle == 0:
                rotated = processed
                should_close = False
            else:
                rotated = processed.rotate(angle, expand=True)
                should_close = True

            try:
                config = (
                    DEFAULT_TESSERACT_CONFIG
                    if angle in {0, 180}
                    else VERTICAL_TESSERACT_CONFIG
                )
                text = _perform_ocr(rotated, lang=lang, config=config, angle=angle)
            finally:
                if should_close:
                    rotated.close()

            score = _score_text(text)
            if score > best_score:
                best_score = score
                best_text = text

        return best_text.strip()
    finally:
        processed.close()
        image.close()


def _load_image(image_bytes: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        raise ValueError("画像を読み込めませんでした。") from exc


def _preprocess_image(image: Image.Image) -> Image.Image:
    grayscale = image.convert("L")
    contrasted = ImageOps.autocontrast(grayscale)
    enhanced = ImageEnhance.Contrast(contrasted).enhance(1.25)
    sharpened = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=140, threshold=3))
    denoised = sharpened.filter(ImageFilter.MedianFilter(size=3))

    def _threshold(value: int) -> int:
        return 255 if value > 135 else 0

    binary = denoised.point(_threshold)
    return binary.convert("L")


def _detect_rotation(image: Image.Image) -> int:
    if pytesseract is None:
        return 0
    try:
        osd_text = pytesseract.image_to_osd(image)  # type: ignore[attr-defined]
    except Exception:
        return 0
    match = re.search(r"Rotate:\s*(\d+)", osd_text or "")
    if not match:
        return 0
    try:
        return int(match.group(1)) % 360
    except ValueError:
        return 0


def _generate_candidate_angles(rotation_hint: int) -> List[int]:
    base_candidates = [rotation_hint, 0, 90, 270, 180]
    seen: set[int] = set()
    ordered: List[int] = []
    for angle in base_candidates:
        normalised = angle % 360
        if normalised in seen:
            continue
        seen.add(normalised)
        ordered.append(normalised)
    return ordered


def _perform_ocr(image: Image.Image, *, lang: str, config: str, angle: int = 0) -> str:
    if pytesseract is None:
        return ""
    try:
        text = pytesseract.image_to_string(image, lang=lang, config=config)  # type: ignore[call-arg]
    except Exception:
        text = ""
    if text.strip():
        return text
    if lang != "eng":
        try:
            fallback = pytesseract.image_to_string(image, lang="eng", config=config)  # type: ignore[call-arg]
        except Exception:
            fallback = ""
        return fallback
    return text


def _score_text(text: str) -> float:
    stripped = text.strip()
    if not stripped:
        return float("-inf")
    length = len(stripped)
    japanese_chars = len(_JAPANESE_CHAR_PATTERN.findall(stripped))
    digit_bonus = len(re.findall(r"\d", stripped)) * 0.05
    length_bonus = min(length / 80.0, 3.0)
    return japanese_chars * 2.0 + length_bonus + digit_bonus
