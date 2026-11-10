from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    VIDEO_URL = "video_url"
    PODCAST_EPISODE = "podcast_episode"
    LOCAL_AUDIO = "local_audio"
    LOCAL_VIDEO = "local_video"
    EPUB = "epub"


class Platform(StrEnum):
    BILIBILI = "bilibili"
    YOUTUBE = "youtube"
    PODCAST = "podcast"
    LOCAL = "local"


class ConsumptionState(StrEnum):
    UNSTARTED = "unstarted"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class RunState(StrEnum):
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


STAGE_DOWNLOADING = "downloading"
STAGE_EXTRACTING_AUDIO = "extracting_audio"
STAGE_EXTRACTING_TEXT = "extracting_text"
STAGE_TRANSCRIBING = "transcribing"
STAGE_ORGANIZING = "organizing"
STAGE_INDEXING = "indexing"

ACTIVE_RUN_STATES = frozenset(
    {
        RunState.QUEUED,
        STAGE_DOWNLOADING,
        STAGE_EXTRACTING_AUDIO,
        STAGE_EXTRACTING_TEXT,
        STAGE_TRANSCRIBING,
        STAGE_ORGANIZING,
        STAGE_INDEXING,
    }
)
TERMINAL_RUN_STATES = frozenset({RunState.COMPLETED, RunState.FAILED, RunState.CANCELLED})

STAGES_BY_SOURCE: dict[str, tuple[str, ...]] = {
    SourceType.VIDEO_URL: (
        STAGE_DOWNLOADING,
        STAGE_EXTRACTING_AUDIO,
        STAGE_TRANSCRIBING,
        STAGE_ORGANIZING,
        STAGE_INDEXING,
    ),
    SourceType.PODCAST_EPISODE: (
        STAGE_DOWNLOADING,
        STAGE_EXTRACTING_AUDIO,
        STAGE_TRANSCRIBING,
        STAGE_ORGANIZING,
        STAGE_INDEXING,
    ),
    SourceType.LOCAL_AUDIO: (
        STAGE_EXTRACTING_AUDIO,
        STAGE_TRANSCRIBING,
        STAGE_ORGANIZING,
        STAGE_INDEXING,
    ),
    SourceType.LOCAL_VIDEO: (
        STAGE_EXTRACTING_AUDIO,
        STAGE_TRANSCRIBING,
        STAGE_ORGANIZING,
        STAGE_INDEXING,
    ),
    SourceType.EPUB: (
        STAGE_EXTRACTING_TEXT,
        STAGE_ORGANIZING,
        STAGE_INDEXING,
    ),
}

STAGE_LABELS = {
    "queued": "Queued",
    STAGE_DOWNLOADING: "Downloading",
    STAGE_EXTRACTING_AUDIO: "Extracting audio",
    STAGE_EXTRACTING_TEXT: "Extracting text",
    STAGE_TRANSCRIBING: "Transcribing",
    STAGE_ORGANIZING: "Organizing",
    STAGE_INDEXING: "Indexing",
    "completed": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}

SOURCE_TYPE_LABELS: dict[str, str] = {
    SourceType.VIDEO_URL: "Video",
    SourceType.PODCAST_EPISODE: "Podcast",
    SourceType.LOCAL_AUDIO: "Audio",
    SourceType.LOCAL_VIDEO: "Video",
    SourceType.EPUB: "Book",
}

PLATFORM_LABELS: dict[str, str] = {
    Platform.BILIBILI: "Bilibili",
    Platform.YOUTUBE: "YouTube",
    Platform.PODCAST: "Podcast",
    Platform.LOCAL: "Local",
}

CONSUMPTION_LABELS: dict[str, str] = {
    ConsumptionState.UNSTARTED: "Unstarted",
    ConsumptionState.IN_PROGRESS: "In progress",
    ConsumptionState.FINISHED: "Finished",
}

ASR_NOT_INSTALLED_HINT = "ASR components are not installed; run: uv sync --extra asr"
ASR_MODEL_MISSING_HINT = "ASR model is not downloaded; run: uv run trove setup"

ERROR_LABELS = {
    "download.network": "Network error; download failed",
    "download.login_required": "Sign-in or cookies required to download",
    "download.geo_restricted": "Content is not available in your region",
    "download.unsupported": "Unsupported video type or URL",
    "download.parse": "Could not parse video info",
    "download.tool_missing": "yt-dlp is missing; install it first",
    "download.too_large": "Media file exceeds the size limit",
    "download.invalid_type": "Unsupported media type",
    "ffmpeg.missing": "FFmpeg/ffprobe is missing; install it first",
    "ffmpeg.failed": "Audio extraction failed",
    "asr.not_configured": ASR_NOT_INSTALLED_HINT,
    "asr.model_missing": ASR_MODEL_MISSING_HINT,
    "asr.failed": "Transcription failed",
    "llm.not_configured": "Organization service is not configured",
    "llm.invalid_output": "Organization output format is invalid",
    "llm.limit_exceeded": "Model call or token limit exceeded",
    "llm.failed": "Organization request failed",
    "epub.invalid": "Not a valid EPUB file",
    "epub.drm": "EPUB is DRM-protected and cannot be imported",
    "epub.fixed_layout": (
        "Only reflowable EPUBs are supported; fixed-layout books cannot be imported"
    ),
    "epub.parse": "EPUB parsing failed",
    "storage.error": "Failed to write the content package",
    "storage.source_missing": "Source file or package metadata is missing",
    "run.reclaimed": "Host restarted; run requeued",
    "internal.error": "Internal error",
}


def stages_for(source_type: str) -> tuple[str, ...]:
    try:
        return STAGES_BY_SOURCE[source_type]
    except KeyError as exc:
        raise ValueError(f"unsupported source type: {source_type}") from exc


def error_label(code: str | None) -> str:
    if not code:
        return "Unknown error"
    return ERROR_LABELS.get(code, f"Processing failed ({code})")
