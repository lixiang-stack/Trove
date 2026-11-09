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
    "queued": "排队中",
    STAGE_DOWNLOADING: "下载中",
    STAGE_EXTRACTING_AUDIO: "抽取音频",
    STAGE_EXTRACTING_TEXT: "提取书文本",
    STAGE_TRANSCRIBING: "转写中",
    STAGE_ORGANIZING: "整理中",
    STAGE_INDEXING: "建立索引",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}

SOURCE_TYPE_LABELS: dict[str, str] = {
    SourceType.VIDEO_URL: "视频",
    SourceType.PODCAST_EPISODE: "播客",
    SourceType.LOCAL_AUDIO: "音频",
    SourceType.LOCAL_VIDEO: "视频",
    SourceType.EPUB: "书",
}

PLATFORM_LABELS: dict[str, str] = {
    Platform.BILIBILI: "Bilibili",
    Platform.YOUTUBE: "YouTube",
    Platform.PODCAST: "播客",
    Platform.LOCAL: "本地",
}

CONSUMPTION_LABELS: dict[str, str] = {
    ConsumptionState.UNSTARTED: "未开始",
    ConsumptionState.IN_PROGRESS: "进行中",
    ConsumptionState.FINISHED: "已完成",
}

ERROR_LABELS = {
    "download.network": "网络错误，下载失败",
    "download.login_required": "需要登录或 cookies 才能下载",
    "download.geo_restricted": "内容在当前地区不可用",
    "download.unsupported": "不支持的视频类型或链接",
    "download.parse": "无法解析视频信息",
    "download.tool_missing": "缺少 yt-dlp，请先安装",
    "download.too_large": "媒体文件超过大小限制",
    "download.invalid_type": "媒体类型不受支持",
    "ffmpeg.missing": "缺少 FFmpeg/ffprobe，请先安装",
    "ffmpeg.failed": "抽取音频失败",
    "asr.not_configured": "转写组件尚未配置",
    "asr.failed": "转写失败",
    "llm.not_configured": "整理组件尚未配置",
    "llm.invalid_output": "整理结果格式无效",
    "llm.limit_exceeded": "超过模型调用或 token 限额",
    "epub.invalid": "不是有效的 EPUB 文件",
    "epub.drm": "EPUB 受 DRM 保护，无法导入",
    "epub.fixed_layout": "仅支持可重排 EPUB，固定版式书无法导入",
    "epub.parse": "EPUB 解析失败",
    "storage.error": "写入内容包失败",
    "run.reclaimed": "Host 重启，已重新排队",
    "internal.error": "内部错误",
}


def stages_for(source_type: str) -> tuple[str, ...]:
    try:
        return STAGES_BY_SOURCE[source_type]
    except KeyError as exc:
        raise ValueError(f"unsupported source type: {source_type}") from exc


def error_label(code: str | None) -> str:
    if not code:
        return "未知错误"
    return ERROR_LABELS.get(code, f"处理失败（{code}）")
