from __future__ import annotations

import re
import unicodedata

_HTML_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_CJK_RANGES = (
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x3040, 0x30FF),
    (0xAC00, 0xD7AF),
)
_LATIN_RE = re.compile(r"[0-9a-z]+(?:[._+-][0-9a-z]+)*")
MAX_QUERY_LENGTH = 200


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return any(start <= code <= end for start, end in _CJK_RANGES)


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = _HTML_RE.sub(" ", value)
    value = value.casefold()
    return _WHITESPACE_RE.sub(" ", value).strip()


def _scan(normalized: str):
    position = 0
    while position < len(normalized):
        char = normalized[position]
        if _is_cjk(char):
            start = position
            while position < len(normalized) and _is_cjk(normalized[position]):
                position += 1
            yield "cjk", normalized[start:position]
            continue
        latin = _LATIN_RE.match(normalized, position)
        if latin:
            yield "latin", latin.group(0)
            position = latin.end()
            continue
        position += 1


def document_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for kind, unit in _scan(normalize_text(value)):
        if kind == "cjk" and len(unit) > 1:
            tokens.extend(unit[index : index + 2] for index in range(len(unit) - 1))
        else:
            tokens.append(unit)
    return tokens


def norm_text(value: str) -> str:
    return " ".join(document_tokens(value))


def query_tokens(query: str) -> list[str]:
    query = normalize_text(query)
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Query is too long; maximum {MAX_QUERY_LENGTH} characters")
    return document_tokens(query)


def build_match_query(query: str) -> tuple[str | None, list[str]]:
    """Build a safe FTS5 MATCH expression.

    Returns (match, like_terms). ``match`` is None when no FTS expression is usable.
    Single CJK characters fall back to LIKE because the index only stores bigrams.
    """
    normalized = normalize_text(query)
    if len(normalized) > MAX_QUERY_LENGTH:
        raise ValueError(f"Query is too long; maximum {MAX_QUERY_LENGTH} characters")
    phrases: list[str] = []
    like_terms: list[str] = []
    for kind, unit in _scan(normalized):
        if kind == "latin":
            phrases.append('"' + unit + '"')
        elif len(unit) == 1:
            like_terms.append(unit)
        else:
            bigrams = [unit[index : index + 2] for index in range(len(unit) - 1)]
            phrases.append('"' + " ".join(bigrams) + '"')
    match = " AND ".join(phrases) if phrases else None
    return match, like_terms


def query_words(query: str) -> list[str]:
    """Keep phrase-like CJK runs and Latin words for snippets and highlighting."""
    return [unit for _kind, unit in _scan(normalize_text(query))]


def snippet(text: str, query: str, *, max_chars: int = 180) -> str:
    value = text or ""
    if len(value) <= max_chars:
        return value
    terms = query_words(query)
    folded = value.casefold()
    positions = [folded.find(term) for term in terms]
    found = [position for position in positions if position >= 0]
    if not found:
        return value[:max_chars].rstrip() + "…"
    index = min(found)
    start = max(0, index - max_chars // 3)
    end = min(len(value), start + max_chars)
    start = max(0, end - max_chars)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(value) else ""
    return prefix + value[start:end].strip() + suffix


def ref_label(doc_kind: str, ref: str) -> str:
    if doc_kind == "transcript":
        parts = ref.split(":")
        if len(parts) == 2 and parts[1].isdigit():
            seconds = int(parts[1]) // 1000
            return f"transcript · {seconds // 60:02d}:{seconds % 60:02d}"
        return "transcript"
    if doc_kind == "book":
        return f"Book · {ref}"
    if doc_kind == "title":
        return "Title"
    if doc_kind == "summary":
        return "Summary"
    if doc_kind == "tag":
        return "Tag"
    return doc_kind
