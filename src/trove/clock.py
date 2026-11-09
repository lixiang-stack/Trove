from __future__ import annotations

import time
from datetime import UTC, datetime


def utc_ms() -> int:
    return int(time.time() * 1000)


def iso_from_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()
