from __future__ import annotations

import pytest

from trove.domain.search import build_match_query, document_tokens, norm_text, ref_label
from trove.domain.tags import normalize_tag
from trove.errors import ValidationError


def test_cjk_bigram_normalization():
    assert document_tokens("人工智能") == ["人工", "工智", "智能"]
    assert document_tokens("记忆") == ["记忆"]
    assert document_tokens("中") == ["中"]


def test_mixed_language_and_html_normalization():
    assert norm_text("<b>AI</b> 记忆") == "ai 记忆"
    assert document_tokens("AI agents") == ["ai", "agents"]
    assert norm_text("  Ｈｅｌｌｏ   World ") == "hello world"


def test_build_match_query_uses_phrases_for_cjk():
    match, like_terms = build_match_query("人工智能")
    assert match == '"人工 工智 智能"'
    assert like_terms == []


def test_build_match_query_mixes_cjk_and_latin():
    match, like_terms = build_match_query("AI 记忆")
    assert match == '"ai" AND "记忆"'
    assert like_terms == []


def test_single_cjk_character_falls_back_to_like():
    match, like_terms = build_match_query("字")
    assert match is None
    assert like_terms == ["字"]


def test_query_length_is_bounded():
    with pytest.raises(ValueError):
        build_match_query("a" * 201)


def test_tag_normalization():
    assert normalize_tag("  #Memory ") == ("Memory", "memory")
    assert normalize_tag("Agents") == ("Agents", "agent")
    assert normalize_tag("记忆") == ("记忆", "记忆")
    with pytest.raises(ValidationError):
        normalize_tag("   ")


def test_ref_labels():
    assert ref_label("transcript", "3:65000") == "transcript · 01:05"
    assert ref_label("book", "2:4") == "书 · 2:4"
    assert ref_label("title", "title") == "标题"
