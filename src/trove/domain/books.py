from __future__ import annotations

import re
import unicodedata

PLACEHOLDER_TITLES = {
    "untitled",
    "untitled book",
    "untitled content",
    "unknown",
    "no title",
    "未知",
    "未命名",
    "无名",
    "无标题",
}
_HEX_TITLE_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)
_UUID_TITLE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def meaningful_title(value: str | None) -> str | None:
    title = unicodedata.normalize("NFKC", value or "").strip()
    if not title:
        return None
    if title.casefold() in PLACEHOLDER_TITLES:
        return None
    if _HEX_TITLE_RE.fullmatch(title) or _UUID_TITLE_RE.fullmatch(title):
        return None
    return title
