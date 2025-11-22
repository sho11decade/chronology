from __future__ import annotations

import pytest

try:
    from .mecab_analyzer import extract_named_entities, has_mecab, tokenize
except ImportError:  # pragma: no cover
    from mecab_analyzer import extract_named_entities, has_mecab, tokenize  # type: ignore


@pytest.mark.skipif(not has_mecab(), reason="MeCab が利用できない環境です")
def test_tokenize_returns_morphemes():
    tokens = tokenize("徳川家康が江戸に入府した。")
    surfaces = [token.surface for token in tokens]
    assert "徳川家康" in surfaces
    assert "江戸" in surfaces
    entities = extract_named_entities(tokens)
    assert "徳川家康" in entities
