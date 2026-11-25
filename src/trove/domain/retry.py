from __future__ import annotations

import errno
import random
from collections.abc import Callable, Mapping
from typing import Any

from trove.domain.items import (
    DEFAULT_MAX_ATTEMPTS,
    STAGE_DOWNLOADING,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_INDEXING,
    STAGE_ORGANIZING,
    STAGE_TRANSCRIBING,
)

RETRYABLE_ERROR_CODES = frozenset({"download.network", "llm.failed"})
TRANSIENT_ERROR_CODES = frozenset({"asr.failed", "storage.error"})

STAGE_MAX_ATTEMPTS: dict[str, int] = {
    STAGE_DOWNLOADING: 3,
    STAGE_EXTRACTING_AUDIO: 3,
    STAGE_EXTRACTING_TEXT: 3,
    STAGE_TRANSCRIBING: 1,
    STAGE_ORGANIZING: 3,
    STAGE_INDEXING: 2,
}
RETRY_DELAYS_MS = (30_000, 120_000, 600_000)
RETRY_JITTER_RATIO = 0.2
MIN_LEASE_ATTEMPTS = 2
TRANSIENT_OS_ERRNOS = frozenset(
    {errno.EAGAIN, errno.EBUSY, errno.EINTR, errno.ETIMEDOUT, errno.ENOSPC}
)


def is_transient_os_error(exc: OSError) -> bool:
    return exc.errno in TRANSIENT_OS_ERRNOS


def is_retryable(code: str, details: Mapping[str, Any] | None = None) -> bool:
    if code in TRANSIENT_ERROR_CODES:
        return bool(details and details.get("transient") is True)
    if code == "llm.failed":
        status = details.get("status") if details is not None else None
        return status is None or status == 429 or status >= 500
    return code in RETRYABLE_ERROR_CODES


def max_attempts_for(stage: str, overrides: Mapping[str, int] | None = None) -> int:
    if overrides is not None and stage in overrides:
        return overrides[stage]
    return STAGE_MAX_ATTEMPTS.get(stage, DEFAULT_MAX_ATTEMPTS)


def retry_delay_ms(
    attempt: int,
    *,
    jitter: Callable[[], float] | None = None,
) -> int:
    index = min(max(attempt, 1), len(RETRY_DELAYS_MS)) - 1
    draw = (jitter or random.random)()
    factor = 1 + RETRY_JITTER_RATIO * (2 * draw - 1)
    return max(0, int(RETRY_DELAYS_MS[index] * factor))
