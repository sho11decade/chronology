from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, TYPE_CHECKING, Protocol, cast

try:  # pragma: no cover - runtime fallback when MeCab is unavailable
    import fugashi  # type: ignore[import]
except ImportError:  # pragma: no cover - runtime fallback when MeCab is unavailable
    fugashi = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - type checking helper
    class FugashiTagger(Protocol):
        def __call__(self, text: str) -> Iterable[Any]:  # pragma: no cover - typing only
            ...

        def __iter__(self) -> Iterable[Any]:  # pragma: no cover - typing only
            ...
else:
    FugashiTagger = Any  # type: ignore[misc]


@dataclass(frozen=True)
class Morpheme:
    surface: str
    base_form: str
    pos: str
    pos_detail: str
    pos_subclass: str = ""


_tagger: Optional[Any] = None
_tagger_initialised: bool = False


def _initialise_tagger() -> None:
    global _tagger, _tagger_initialised
    if _tagger_initialised:
        return
    _tagger_initialised = True
    if fugashi is None:
        return
    try:
        tagger_cls = getattr(fugashi, "Tagger", None)
        if not callable(tagger_cls):
            return
        _tagger = cast("FugashiTagger", tagger_cls())
    except Exception:
        _tagger = None


def has_mecab() -> bool:
    _initialise_tagger()
    return _tagger is not None


_MERGEABLE_POS_DETAILS = {"固有名詞", "人名", "地域", "地名"}


def _merge_compound_morphemes(morphemes: List[Morpheme]) -> List[Morpheme]:
    merged: List[Morpheme] = []
    buffer: List[Morpheme] = []

    def flush_buffer() -> None:
        if not buffer:
            return
        surface = "".join(item.surface for item in buffer)
        base_joined = "".join(item.base_form for item in buffer if item.base_form)
        pos = buffer[0].pos
        pos_detail = buffer[0].pos_detail
        pos_subclass = buffer[0].pos_subclass
        merged.append(
            Morpheme(
                surface=surface,
                base_form=base_joined or surface,
                pos=pos,
                pos_detail=pos_detail,
                pos_subclass=pos_subclass,
            )
        )
        buffer.clear()

    for morph in morphemes:
        if morph.pos == "名詞" and morph.pos_detail in _MERGEABLE_POS_DETAILS:
            buffer.append(morph)
            continue
        flush_buffer()
        merged.append(morph)

    flush_buffer()
    return merged


def tokenize(text: str) -> List[Morpheme]:
    _initialise_tagger()
    if not _tagger:
        return []
    raw_results: List[Morpheme] = []
    for token in _tagger(text):
        features = getattr(token, "feature", None)
        pos = getattr(features, "pos1", getattr(token, "pos", ""))
        pos_detail = getattr(features, "pos2", getattr(features, "pos1", ""))
        pos_subclass = getattr(features, "pos3", "")
        base = getattr(features, "lemma", token.surface)
        raw_results.append(
            Morpheme(
                surface=token.surface,
                base_form=base or token.surface,
                pos=pos or "",
                pos_detail=pos_detail or "",
                pos_subclass=pos_subclass or "",
            )
        )
    if not raw_results:
        return raw_results
    return _merge_compound_morphemes(raw_results)


def extract_named_entities(tokens: Iterable[Morpheme]) -> List[str]:
    entities: List[str] = []
    for morph in tokens:
        if morph.pos == "名詞" and morph.pos_detail == "固有名詞":
            entities.append(morph.surface)
    return entities


def filter_by_pos(tokens: Iterable[Morpheme], *, pos: str) -> List[str]:
    return [m.surface for m in tokens if m.pos == pos]
