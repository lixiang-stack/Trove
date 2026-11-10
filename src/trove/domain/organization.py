from __future__ import annotations

from trove.domain.search import is_cjk
from trove.domain.tags import normalize_tag
from trove.errors import ValidationError

MAX_EXISTING_TAGS = 100


def chunk_text(text: str, chunk_chars: int) -> list[str]:
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    chunks: list[str] = []
    current: list[str] = []
    for line in (text or "").splitlines(keepends=True):
        while len(line) > chunk_chars:
            if current:
                chunks.append("".join(current))
                current = []
            chunks.append(line[:chunk_chars])
            line = line[chunk_chars:]
        if current and len("".join(current)) + len(line) > chunk_chars:
            chunks.append("".join(current))
            current = []
        current.append(line)
    if current:
        chunks.append("".join(current))
    return [chunk for chunk in chunks if chunk]


def estimate_tokens(text: str) -> int:
    cjk = sum(1 for char in text or "" if is_cjk(char))
    other = len(text or "") - cjk
    return cjk + (other + 3) // 4


def estimate_cost(
    input_tokens: int, output_tokens: int, input_rate: float, output_rate: float
) -> float:
    return round(
        (input_tokens / 1_000_000) * input_rate
        + (output_tokens / 1_000_000) * output_rate,
        8,
    )


def normalize_tags(raw_tags: list[str], *, limit: int = 5) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for raw in raw_tags:
        try:
            display, normalized = normalize_tag(str(raw))
        except ValidationError:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(display)
        if len(tags) == limit:
            break
    return tags
