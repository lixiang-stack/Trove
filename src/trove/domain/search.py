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


def document_tokens(value: str) -> list[str]:
    normalized = normalize_text(value)
    tokens: list[str] = []
    cjk_run: list[str] = []

    def flush_cjk() -> None:
        nonlocal cjk_run
        if not cjk_run:
            return
        if len(cjk_run) == 1:
            tokens.append(cjk_run[0])
        else:
            tokens.extend("".join(cjk_run[index : index + 2]) for index in range(len(cjk_run) - 1))
        cjk_run = []

    position = 0
    while position < len(normalized):
        char = normalized[position]
        if _is_cjk(char):
            cjk_run.append(char)
            position += 1
            continue
        flush_cjk()
        match = _LATIN_RE.match(normalized, position)
        if match:
            tokens.append(match.group(0))
            position = match.end()
            continue
        position += 1
    flush_cjk()
    return list(dict.fromkeys(token for token in tokens if token))


def norm_text(value: str) -> str:
    return " ".join(document_tokens(value))


def query_tokens(query: str) -> list[str]:
    query = normalize_text(query)
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"query longer than {MAX_QUERY_LENGTH} characters")
    return document_tokens(query)


def build_match_query(query: str) -> tuple[str | None, list[str]]:
    """Build a safe FTS5 MATCH expression.

    Returns (match, like_terms). ``match`` is None when no FTS expression is usable.
    Single CJK characters fall back to LIKE because the index only stores bigrams.
    """
    normalized = normalize_text(query)
    if len(normalized) > MAX_QUERY_LENGTH:
        raise ValueError(f"query longer than {MAX_QUERY_LENGTH} characters")
    phrases: list[str] = []
    like_terms: list[str] = []
    position = 0
    while position < len(normalized):
        char = normalized[position]
        if _is_cjk(char):
            start = position
            while position < len(normalized) and _is_cjk(normalized[position]):
                position += 1
            run = normalized[start:position]
            if len(run) == 1:
                like_terms.append(run)
            else:
                bigrams = [run[index : index + 2] for index in range(len(run) - 1)]
                phrases.append('"' + " ".join(bigrams) + '"')
            continue
        latin = _LATIN_RE.match(normalized, position)
        if latin:
            phrases.append('"' + latin.group(0) + '"')
            position = latin.end()
            continue
        position += 1
    match = " AND ".join(phrases) if phrases else None
    return match, like_terms


def ref_label(doc_kind: str, ref: str) -> str:
    if doc_kind == "transcript":
        parts = ref.split(":")
        if len(parts) == 2 and parts[1].isdigit():
            seconds = int(parts[1]) // 1000
            return f"transcript · {seconds // 60:02d}:{seconds % 60:02d}"
        return "transcript"
    if doc_kind == "book":
        return f"书 · {ref}"
    if doc_kind == "title":
        return "标题"
    if doc_kind == "summary":
        return "摘要"
    if doc_kind == "tag":
        return "Tag"
    return doc_kind
