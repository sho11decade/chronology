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
FAST_PROBE_DIMENSION = 1024
FAST_PROBE_TIMEOUT_SECONDS = 6
FAST_FALLBACK_DIMENSION = 900
FAST_FALLBACK_TIMEOUT_SECONDS = 5
FAST_FALLBACK_CONFIG = "--oem 1 --psm 7 -c preserve_interword_spaces=1"
TESSERACT_TIMEOUT_SECONDS = 12
GOOD_SCORE_THRESHOLD = 35.0
MEDIAN_FILTER_THRESHOLD = 1_200_000  # ピクセル数
UNSHARP_FILTER_THRESHOLD = 250_000
DEFAULT_ANGLE_ORDER = [0, 180, 90, 270]


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
    try:
        last_result = ""
        for max_dimension in (MAX_OCR_DIMENSION, FALLBACK_OCR_DIMENSION):
            working = _prepare_for_ocr(image, max_dimension=max_dimension)
            try:
                text = ""
                angles = _determine_rotation_order(working, lang=lang)
                processed = _preprocess_image(working)
                try:
                    text = _run_ocr_candidates(
                        processed,
                        angles=angles,
                        lang=lang,
                    )
                finally:
                    processed.close()
            finally:
                working.close()

            stripped = text.strip()
            if stripped:
                return stripped
            last_result = text

        fallback_text = _lightweight_ocr(image, lang=lang)
        if fallback_text.strip():
            return fallback_text.strip()
        return last_result.strip()
    finally:
        image.close()


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
    width, height = contrasted.size
    pixel_count = width * height

    enhanced = ImageEnhance.Contrast(contrasted).enhance(1.2 if pixel_count < 600_000 else 1.3)

    if pixel_count >= UNSHARP_FILTER_THRESHOLD:
        sharpened = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=140, threshold=3))
    else:
        sharpened = enhanced

    if pixel_count >= MEDIAN_FILTER_THRESHOLD:
        denoised = sharpened.filter(ImageFilter.MedianFilter(size=3))
    else:
        denoised = sharpened

    def _threshold(value: int) -> int:
        return 255 if value > 135 else 0

    binary = denoised.point(_threshold)
    return binary.convert("L")


def _run_ocr_candidates(image: Image.Image, *, angles: List[int], lang: str) -> str:
    best_text = ""
    best_score = float("-inf")

    for angle in angles or DEFAULT_ANGLE_ORDER:
        with _candidate_view(image, angle) as candidate:
            config = _config_for_angle(angle)
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


def _determine_rotation_order(image: Image.Image, *, lang: str) -> List[int]:
    if pytesseract is None:
        return list(DEFAULT_ANGLE_ORDER)

    try:
        probe = _create_probe_image(image)
    except Exception:
        return list(DEFAULT_ANGLE_ORDER)

    try:
        scored: List[tuple[float, int]] = []
        for angle in DEFAULT_ANGLE_ORDER:
            with _candidate_view(probe, angle) as candidate:
                config = _config_for_angle(angle)
                text = _perform_ocr(
                    candidate,
                    lang=lang,
                    config=config,
                    timeout=FAST_PROBE_TIMEOUT_SECONDS,
                    use_fallback=False,
                )
            score = _score_text(text)
            scored.append((score, angle))

        scored.sort(key=lambda item: item[0], reverse=True)
        ordered = [angle for score, angle in scored if score > float("-inf")]
        if not ordered:
            return list(DEFAULT_ANGLE_ORDER)
        for angle in DEFAULT_ANGLE_ORDER:
            if angle not in ordered:
                ordered.append(angle)
        return ordered[: len(DEFAULT_ANGLE_ORDER)]
    finally:
        probe.close()


def _create_probe_image(image: Image.Image) -> Image.Image:
    base = image.copy()
    if max(base.size) > FAST_PROBE_DIMENSION:
        try:
            resized = _prepare_for_ocr(base, max_dimension=FAST_PROBE_DIMENSION)
        finally:
            base.close()
        return resized
    return base


def _lightweight_ocr(image: Image.Image, *, lang: str) -> str:
    if pytesseract is None:
        return ""
    base = _prepare_for_ocr(image, max_dimension=FAST_FALLBACK_DIMENSION)
    try:
        best_text = ""
        best_score = float("-inf")
        for angle in DEFAULT_ANGLE_ORDER:
            with _candidate_view(base, angle) as candidate:
                text = _perform_ocr(
                    candidate,
                    lang=lang,
                    config=FAST_FALLBACK_CONFIG,
                    timeout=FAST_FALLBACK_TIMEOUT_SECONDS,
                    use_fallback=False,
                )
            score = _score_text(text)
            if score > best_score:
                best_score = score
                best_text = text
            if best_score >= GOOD_SCORE_THRESHOLD:
                break
        return best_text
    finally:
        base.close()


def _config_for_angle(angle: int) -> str:
    return DEFAULT_TESSERACT_CONFIG if angle % 180 == 0 else VERTICAL_TESSERACT_CONFIG


@contextmanager
def _candidate_view(image: Image.Image, angle: int):
    normalised = angle % 360
    if normalised == 0:
        yield image
        return

    rotated = _rotate_image_fast(image, normalised)

    try:
        yield rotated
    finally:
        rotated.close()


def _rotate_image_fast(image: Image.Image, angle: int) -> Image.Image:
    """90 度刻みは transpose を使ってメモリと時間を節約する。"""
    normalised = angle % 360
    if normalised in {90, 180, 270}:
        attr_name = f"ROTATE_{normalised}"
        rotate_const = getattr(Image, attr_name, None)
        if rotate_const is not None:
            try:
                return image.transpose(rotate_const)
            except Exception:
                pass
    return image.rotate(normalised, expand=True)


def _perform_ocr(
    image: Image.Image,
    *,
    lang: str,
    config: str,
    timeout: int | None = None,
    use_fallback: bool = True,
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
    if use_fallback and lang != "eng":
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
