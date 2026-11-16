from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BookLocator:
    chapter_index: int
    paragraph_index: int | None = None
    scroll_ratio: float = 0.0
    epub_href: str | None = None
    epub_progression: float | None = None
    epub_total_progression: float | None = None

    @property
    def is_epub(self) -> bool:
        return bool(self.epub_href)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _optional_ratio(data: dict, key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if not _is_number(value):
        raise ValueError(f"{key} must be a number")
    return min(max(float(value), 0.0), 1.0)


def parse_book_locator(raw: str | None) -> BookLocator | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    schema = data.get("schema")
    if schema is not None and schema != 2:
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
    epub_href = data.get("epub_href")
    if epub_href is not None and not isinstance(epub_href, str):
        return None
    try:
        epub_progression = _optional_ratio(data, "epub_progression")
        epub_total_progression = _optional_ratio(data, "epub_total_progression")
    except ValueError:
        return None
    return BookLocator(
        chapter_index=chapter,
        paragraph_index=paragraph,
        scroll_ratio=min(max(float(scroll), 0.0), 1.0),
        epub_href=epub_href or None,
        epub_progression=epub_progression,
        epub_total_progression=epub_total_progression,
    )


def serialize_book_locator(locator: BookLocator) -> str:
    if not locator.is_epub:
        return json.dumps(
            {
                "chapter_index": locator.chapter_index,
                "paragraph_index": locator.paragraph_index,
                "scroll_ratio": round(locator.scroll_ratio, 4),
            },
            separators=(",", ":"),
        )
    return json.dumps(
        {
            "schema": 2,
            "chapter_index": locator.chapter_index,
            "paragraph_index": locator.paragraph_index,
            "scroll_ratio": round(locator.scroll_ratio, 4),
            "epub_href": locator.epub_href,
            "epub_progression": (
                round(locator.epub_progression, 6)
                if locator.epub_progression is not None
                else None
            ),
            "epub_total_progression": (
                round(locator.epub_total_progression, 6)
                if locator.epub_total_progression is not None
                else None
            ),
        },
        separators=(",", ":"),
    )
