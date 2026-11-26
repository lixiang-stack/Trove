from __future__ import annotations

from trove.domain.items import (
    STAGE_DOWNLOADING,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_INDEXING,
    STAGE_ORGANIZING,
    STAGE_TRANSCRIBING,
)

ALL_STAGES = (
    STAGE_DOWNLOADING,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_TRANSCRIBING,
    STAGE_ORGANIZING,
    STAGE_INDEXING,
)

POOL_STAGES: dict[str, frozenset[str]] = {
    "all": frozenset(ALL_STAGES),
    "download": frozenset(
        {STAGE_DOWNLOADING, STAGE_EXTRACTING_AUDIO, STAGE_EXTRACTING_TEXT}
    ),
    "asr": frozenset({STAGE_TRANSCRIBING}),
    "llm": frozenset({STAGE_ORGANIZING}),
    "index": frozenset({STAGE_INDEXING}),
}

POOL_NAMES = tuple(POOL_STAGES)

# The default `trove worker` stays a single serial claimer. Per-pool workers
# use the resource-specific defaults below.
DEFAULT_POOL_CONCURRENCY: dict[str, int] = {
    "all": 1,
    "download": 3,
    "asr": 1,
    "llm": 2,
    "index": 1,
}

INDEX_POOL_CONCURRENCY = 1
