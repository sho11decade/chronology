from __future__ import annotations

import io
import re
from contextlib import contextmanager
from typing import List

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

try:  # pragma: no cover - 環境によっては OCR 依存が未導入
    import pytesseract  # type: ignore[import]
except ImportError:  # pragma: no cover - OCR を使わずに続行
    pytesseract = None  # type: ignore[assignment]

try:
    RESAMPLE_BEST = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
except AttributeError:  # Pillow < 10 互換
    RESAMPLE_BEST = getattr(Image, "LANCZOS", Image.BICUBIC)  # type: ignore[attr-defined]


DEFAULT_TESSERACT_CONFIG = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
VERTICAL_TESSERACT_CONFIG = "--oem 3 --psm 5 -c preserve_interword_spaces=1"
_JAPANESE_CHAR_PATTERN = re.compile(r"[一-龥ぁ-んァ-ヴー々〆ヶー]")

MAX_OCR_DIMENSION = 2400
FALLBACK_OCR_DIMENSION = 1600
OSD_MAX_DIMENSION = 1024
TESSERACT_TIMEOUT_SECONDS = 12
TESSERACT_OSD_TIMEOUT_SECONDS = 5
GOOD_SCORE_THRESHOLD = 35.0


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

    last_result = ""
    for max_dimension in (MAX_OCR_DIMENSION, FALLBACK_OCR_DIMENSION):
        image = _load_image(image_bytes)
        try:
            working = _prepare_for_ocr(image, max_dimension=max_dimension)
            try:
                text = ""
                rotation_hint = _detect_rotation(working)
                processed = _preprocess_image(working)
                try:
                    text = _run_ocr_candidates(
                        processed,
                        rotation_hint=rotation_hint,
                        lang=lang,
                    )
                finally:
                    processed.close()
            finally:
                working.close()
        finally:
            image.close()

        stripped = text.strip()
        if stripped:
            return stripped
        last_result = text

    return last_result.strip()


def _load_image(image_bytes: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(image_bytes))
    except UnidentifiedImageError as exc:
        raise ValueError("画像を読み込めませんでした。") from exc


def _prepare_for_ocr(image: Image.Image, *, max_dimension: int) -> Image.Image:
    """OCR 用に画像サイズを正規化する。"""
    if max_dimension <= 0:
        return image.copy()

    width, height = image.size
    longest = max(width, height)
    if longest <= max_dimension:
        return image.copy()

    scale = max_dimension / float(longest)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, RESAMPLE_BEST)


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


def _run_ocr_candidates(image: Image.Image, *, rotation_hint: int, lang: str) -> str:
    best_text = ""
    best_score = float("-inf")

    for angle in _generate_candidate_angles(rotation_hint):
        with _candidate_view(image, angle) as candidate:
            config = DEFAULT_TESSERACT_CONFIG if angle in {0, 180} else VERTICAL_TESSERACT_CONFIG
            text = _perform_ocr(
                candidate,
                lang=lang,
                config=config,
                timeout=TESSERACT_TIMEOUT_SECONDS,
            )

        score = _score_text(text)
        if score > best_score:
            best_score = score
            best_text = text

        if best_score >= GOOD_SCORE_THRESHOLD:
            break

    return best_text


@contextmanager
def _candidate_view(image: Image.Image, angle: int):
    normalised = angle % 360
    if normalised == 0:
        yield image
        return

    rotated = image.rotate(normalised, expand=True)

    try:
        yield rotated
    finally:
        rotated.close()


def _detect_rotation(image: Image.Image) -> int:
    if pytesseract is None:
        return 0
    downscaled: Image.Image | None = None
    try:
        longest = max(image.size)
        candidate = image
        if longest > OSD_MAX_DIMENSION:
            scale = OSD_MAX_DIMENSION / float(longest)
            new_size = (
                max(1, int(image.width * scale)),
                max(1, int(image.height * scale)),
            )
            downscaled = image.resize(new_size, RESAMPLE_BEST)
            candidate = downscaled

        if TESSERACT_OSD_TIMEOUT_SECONDS:
            osd_text = pytesseract.image_to_osd(  # type: ignore[attr-defined,call-arg]
                candidate,
                timeout=TESSERACT_OSD_TIMEOUT_SECONDS,
            )
        else:
            osd_text = pytesseract.image_to_osd(candidate)  # type: ignore[attr-defined]
    except RuntimeError as exc:
        if "timeout" in str(exc).lower():
            return 0
        return 0
    except Exception:
        return 0
    finally:
        if downscaled is not None:
            downscaled.close()
    match = re.search(r"Rotate:\s*(\d+)", osd_text or "")
    if not match:
        return 0
    try:
        return int(match.group(1)) % 360
    except ValueError:
        return 0


def _generate_candidate_angles(rotation_hint: int) -> List[int]:
    hint = rotation_hint % 360
    if hint in {0, 180}:
        base_candidates = [hint, (hint + 180) % 360, 90, 270]
    elif hint in {90, 270}:
        base_candidates = [hint, (hint + 180) % 360, 0, 180]
    else:
        base_candidates = [hint, 0, 180, 90, 270]
    seen: set[int] = set()
    ordered: List[int] = []
    for angle in base_candidates:
        normalised = angle % 360
        if normalised in seen:
            continue
        seen.add(normalised)
        ordered.append(normalised)
    return ordered


def _perform_ocr(
    image: Image.Image,
    *,
    lang: str,
    config: str,
    timeout: int | None = None,
) -> str:
    if pytesseract is None:
        return ""
    try:
        if timeout is not None:
            text = pytesseract.image_to_string(  # type: ignore[call-arg]
                image,
                lang=lang,
                config=config,
                timeout=timeout,
            )
        else:
            text = pytesseract.image_to_string(image, lang=lang, config=config)  # type: ignore[call-arg]
    except RuntimeError as exc:
        if "timeout" in str(exc).lower():
            text = ""
        else:
            text = ""
    except Exception:
        text = ""
    if text.strip():
        return text
    if lang != "eng":
        try:
            if timeout is not None:
                fallback = pytesseract.image_to_string(  # type: ignore[call-arg]
                    image,
                    lang="eng",
                    config=config,
                    timeout=timeout,
                )
            else:
                fallback = pytesseract.image_to_string(  # type: ignore[call-arg]
                    image,
                    lang="eng",
                    config=config,
                )
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
