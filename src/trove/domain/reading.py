from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BookLocator:
    chapter_index: int
    paragraph_index: int | None = None
    scroll_ratio: float = 0.0


def parse_book_locator(raw: str | None) -> BookLocator | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    chapter = data.get("chapter_index")
    paragraph = data.get("paragraph_index")
    scroll = data.get("scroll_ratio", 0.0)
    if not isinstance(chapter, int) or isinstance(chapter, bool) or chapter < 0:
        return None
    if paragraph is not None and (
        not isinstance(paragraph, int) or isinstance(paragraph, bool) or paragraph < 0
    ):
        return None
    if not isinstance(scroll, (int, float)) or isinstance(scroll, bool):
        return None
    return BookLocator(
        chapter_index=chapter,
        paragraph_index=paragraph,
        scroll_ratio=min(max(float(scroll), 0.0), 1.0),
    )


def serialize_book_locator(locator: BookLocator) -> str:
    return json.dumps(
        {
            "chapter_index": locator.chapter_index,
            "paragraph_index": locator.paragraph_index,
            "scroll_ratio": round(locator.scroll_ratio, 4),
        },
        separators=(",", ":"),
    )
