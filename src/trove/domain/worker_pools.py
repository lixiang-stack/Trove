from __future__ import annotations

from trove.domain.items import (
    ALL_STAGES,
    STAGE_DOWNLOADING,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_INDEXING,
    STAGE_ORGANIZING,
    STAGE_TRANSCRIBING,
)

ALL_POOL = "all"
INDEX_POOL = "index"

POOL_STAGES: dict[str, frozenset[str]] = {
    ALL_POOL: frozenset(ALL_STAGES),
    "download": frozenset(
        {STAGE_DOWNLOADING, STAGE_EXTRACTING_AUDIO, STAGE_EXTRACTING_TEXT}
    ),
    "asr": frozenset({STAGE_TRANSCRIBING}),
    "llm": frozenset({STAGE_ORGANIZING}),
    INDEX_POOL: frozenset({STAGE_INDEXING}),
}

POOL_NAMES = tuple(POOL_STAGES)
