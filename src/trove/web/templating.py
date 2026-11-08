from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

from trove.domain.items import (
    CONSUMPTION_LABELS,
    PLATFORM_LABELS,
    SOURCE_TYPE_LABELS,
    STAGE_LABELS,
    error_label,
)
from trove.domain.search import ref_label

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
COVER_TONES = ("vermilion", "green", "blue", "gold", "ink", "clay")

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def duration(value: float | int | None) -> str:
    if value is None:
        return "—"
    seconds = max(0, int(round(float(value))))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def clock_ms(value: int | None) -> str:
    if value is None:
        return "0:00"
    seconds = max(0, int(value) // 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def datetime_filter(value: int | None) -> str:
    if value is None:
        return "—"
    moment = datetime.fromtimestamp(value / 1000, tz=UTC)
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def cover_tone(item_id: str) -> str:
    digest = hashlib.sha256(item_id.encode("utf-8")).digest()
    return COVER_TONES[digest[0] % len(COVER_TONES)]


templates.env.filters["duration"] = duration
templates.env.filters["clock"] = clock_ms
templates.env.filters["datetime"] = datetime_filter
templates.env.filters["cover_tone"] = cover_tone
templates.env.filters["ref_label"] = ref_label
templates.env.filters["error_label"] = error_label
templates.env.globals.update(
    source_type_labels=SOURCE_TYPE_LABELS,
    platform_labels=PLATFORM_LABELS,
    consumption_labels=CONSUMPTION_LABELS,
    stage_labels=STAGE_LABELS,
)
