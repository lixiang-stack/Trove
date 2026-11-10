from __future__ import annotations

import re
import unicodedata

from trove.errors import ValidationError

TAG_MAX_LENGTH = 64
_WHITESPACE_RE = re.compile(r"\s+")
_HASH_PREFIX_RE = re.compile(r"^[#＃]+")
_TRAILING_PUNCT_RE = re.compile(r"[.,;:!?，。；：！？]+$")

_IRREGULAR_PLURALS = {
    "people": "person",
    "children": "child",
    "men": "man",
    "women": "woman",
    "teeth": "tooth",
    "feet": "foot",
    "mice": "mouse",
    "geese": "goose",
}


def normalize_tag(raw: str) -> tuple[str, str]:
    """Return (display name, normalized name) for a free-form tag."""
    display = unicodedata.normalize("NFKC", raw or "").strip()
    display = _HASH_PREFIX_RE.sub("", display).strip()
    display = _WHITESPACE_RE.sub(" ", display)
    display = _TRAILING_PUNCT_RE.sub("", display)
    if not display:
        raise ValidationError("Tag cannot be empty", details={"code": "tag.empty"})
    if len(display) > TAG_MAX_LENGTH:
        raise ValidationError(
            f"Tag cannot exceed {TAG_MAX_LENGTH} characters", details={"code": "tag.too_long"}
        )
    normalized = unicodedata.normalize("NFKC", display).casefold()
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    if normalized.isascii() and normalized.isalpha():
        normalized = _naive_singular(normalized)
    return display, normalized


def _naive_singular(value: str) -> str:
    if value in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[value]
    if len(value) > 3 and value.endswith("ies"):
        return value[:-3] + "y"
    if len(value) > 3 and value.endswith(("ses", "xes", "zes", "ches", "shes")):
        return value[:-2]
    if len(value) > 3 and value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value
