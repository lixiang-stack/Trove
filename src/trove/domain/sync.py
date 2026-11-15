from __future__ import annotations

from dataclasses import dataclass

from trove.errors import ValidationError

AUDIO_PROGRESS = "audio_progress"
BOOK_PROGRESS = "book_progress"
CONSUMPTION_STATE = "consumption_state"
TAGS = "tags"
HOST_WEB_DEVICE = "host-web"
SYNC_FIELDS = frozenset({AUDIO_PROGRESS, BOOK_PROGRESS, CONSUMPTION_STATE, TAGS})
CLOCK_SKEW_MS = 5 * 60 * 1000


def parse_cursor(value: str | None, *, max_value: int) -> int:
    if value is None or value == "":
        return 0
    try:
        cursor = int(value)
    except ValueError as exc:
        raise _invalid_cursor() from exc
    if cursor < 0 or cursor > max_value:
        raise _invalid_cursor()
    return cursor


@dataclass(frozen=True, slots=True)
class FieldClock:
    client_updated_at: int
    device_id: str


def wins(new: FieldClock, existing: FieldClock | None) -> bool:
    if existing is None:
        return True
    if new.client_updated_at != existing.client_updated_at:
        return new.client_updated_at > existing.client_updated_at
    return new.device_id >= existing.device_id


def normalize_client_time(client_updated_at: int | None, now: int) -> tuple[int, bool]:
    if client_updated_at is None:
        return now, False
    if client_updated_at > now + CLOCK_SKEW_MS:
        return now, True
    return client_updated_at, False


def _invalid_cursor() -> ValidationError:
    return ValidationError(
        "Sync cursor is invalid; perform a full resync",
        details={"code": "sync.cursor_invalid"},
    )
