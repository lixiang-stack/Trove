from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from trove.adapters.feed import download_episode
from trove.adapters.process import run_command
from trove.adapters.safe_http import SafeHttpClient, SafeHttpError
from trove.config import Config
from trove.errors import ProcessingError
from trove.ports import DownloadResult, FeedEpisode, StageContext


class DefaultDownloader:
    def __init__(self, config: Config, http: SafeHttpClient) -> None:
        self.config = config
        self.http = http

    def download(self, source: dict[str, Any], context: StageContext) -> DownloadResult:
        source_type = str(source.get("source_type"))
        if source_type == "podcast_episode":
            return self._download_podcast(source, context)
        return self._download_video(source, context)

    # ------------------------------------------------------------------
    # yt-dlp
    # ------------------------------------------------------------------
    def _download_video(
        self, source: dict[str, Any], context: StageContext
    ) -> DownloadResult:
        if shutil.which(sys.executable) is None:
            raise ProcessingError("download.tool_missing", "缺少 yt-dlp")
        url = str(source.get("source_url_canonical") or source.get("source_url_raw") or "")
        if not url:
            raise ProcessingError("download.unsupported", "缺少视频 URL")
        template = context.work_dir / "download.%(ext)s"
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--no-part",
            "--no-warnings",
            "--print-json",
            "-f",
            "bestaudio/best",
            "-o",
            str(template),
        ]
        if self.config.ytdlp_cookies and self.config.ytdlp_cookies.exists():
            command.extend(["--cookies", str(self.config.ytdlp_cookies)])
        command.append(url)
        result = run_command(
            context,
            command,
            timeout=3600,
            cwd=context.work_dir,
            error_code="download.parse",
        )
        if result.returncode != 0:
            raise _classify_download_error(result.stderr)
        metadata = _last_json(result.stdout)
        path = _downloaded_file(context.work_dir)
        return DownloadResult(
            path=path,
            title=_string(metadata.get("title")),
            author=_string(metadata.get("uploader") or metadata.get("channel")),
            published_at=_upload_date(metadata.get("upload_date")),
            duration_sec=_float(metadata.get("duration")),
            language=_string(metadata.get("language")),
        )

    # ------------------------------------------------------------------
    # Podcast enclosure
    # ------------------------------------------------------------------
    def _download_podcast(
        self, source: dict[str, Any], context: StageContext
    ) -> DownloadResult:
        feed = source.get("feed") or {}
        enclosure_url = feed.get("enclosure_url")
        if not enclosure_url:
            raise ProcessingError("download.unsupported", "播客单集缺少 enclosure")
        episode = FeedEpisode(
            guid=feed.get("episode_guid"),
            title=str(source.get("title") or "未命名单集"),
            author=source.get("author"),
            published_at=source.get("published_at"),
            duration_sec=source.get("duration_sec"),
            enclosure_url=str(enclosure_url),
            enclosure_type=feed.get("enclosure_type"),
            enclosure_size=feed.get("enclosure_size"),
        )
        destination = context.work_dir / "download.media"
        try:
            download_episode(
                self.http,
                episode,
                destination,
                max_bytes=self.config.max_podcast_media_bytes,
            )
        except SafeHttpError as exc:
            raise ProcessingError(exc.code, exc.message) from exc
        return DownloadResult(
            path=destination,
            title=episode.title,
            author=episode.author,
            published_at=episode.published_at,
            duration_sec=episode.duration_sec,
            language=source.get("language"),
        )


def _downloaded_file(work_dir: Path) -> Path:
    candidates = [
        path
        for path in work_dir.iterdir()
        if path.is_file() and path.name.startswith("download.") and not path.name.endswith(".tmp")
    ]
    if not candidates:
        raise ProcessingError("download.parse", "yt-dlp 未产生媒体文件")
    return max(candidates, key=lambda path: path.stat().st_size)


def _last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _classify_download_error(stderr: str) -> ProcessingError:
    text = stderr.lower()
    if re.search(r"sign in|cookies|login|authentication|验证|登录", text):
        return ProcessingError("download.login_required", "下载需要登录或 cookies")
    if re.search(r"not available in your country|geo|region|地区", text):
        return ProcessingError("download.geo_restricted", "内容在当前地区不可用")
    if re.search(r"private video|unsupported url|not a valid url|live event|is live", text):
        return ProcessingError("download.unsupported", "不支持的视频类型或链接")
    if re.search(r"timed out|connection|network|temporary failure|http error", text):
        return ProcessingError("download.network", "网络错误，下载失败")
    return ProcessingError("download.parse", "无法解析视频信息")


def _string(value: Any) -> str | None:
    return str(value) if value else None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _upload_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text
