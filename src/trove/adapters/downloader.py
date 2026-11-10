from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from trove.adapters.feed import download_episode
from trove.adapters.process import run_command
from trove.adapters.safe_http import SafeHttpClient, SafeHttpError
from trove.config import Config
from trove.content_package import SourceDocument
from trove.domain.items import SourceType
from trove.errors import ProcessingError
from trove.ports import (
    DOWNLOAD_MEDIA_FILENAME,
    DownloadResult,
    FeedEpisode,
    StageContext,
)


class DefaultDownloader:
    def __init__(self, config: Config, http: SafeHttpClient) -> None:
        self.config = config
        self.http = http

    def download(self, source: SourceDocument, context: StageContext) -> DownloadResult:
        if source.source_type == SourceType.PODCAST_EPISODE:
            return self._download_podcast(source, context)
        return self._download_video(source, context)

    # ------------------------------------------------------------------
    # yt-dlp
    # ------------------------------------------------------------------
    def _download_video(
        self, source: SourceDocument, context: StageContext
    ) -> DownloadResult:
        if shutil.which(sys.executable) is None:
            raise ProcessingError("download.tool_missing", "yt-dlp is missing")
        url = source.source_url_canonical or source.source_url_raw or ""
        if not url:
            raise ProcessingError("download.unsupported", "Video URL is missing")
        template = context.work_dir / "download.%(ext)s"
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--playlist-items",
            "1",
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
        destination = context.work_dir / DOWNLOAD_MEDIA_FILENAME
        os.replace(path, destination)
        return DownloadResult(
            path=destination,
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
        self, source: SourceDocument, context: StageContext
    ) -> DownloadResult:
        feed = source.feed
        if feed is None or not feed.enclosure_url:
            raise ProcessingError("download.unsupported", "Podcast episode is missing an enclosure")
        episode = FeedEpisode(
            guid=feed.episode_guid,
            title=source.title,
            author=source.author,
            published_at=source.published_at,
            duration_sec=source.duration_sec,
            enclosure_url=feed.enclosure_url,
            enclosure_type=feed.enclosure_type,
            enclosure_size=feed.enclosure_size,
        )
        destination = context.work_dir / DOWNLOAD_MEDIA_FILENAME
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
            language=source.language,
        )


def _downloaded_file(work_dir: Path) -> Path:
    candidates = [
        path
        for path in work_dir.iterdir()
        if path.is_file()
        and path.name.startswith("download.")
        and not path.name.endswith((".tmp", ".part"))
    ]
    if not candidates:
        raise ProcessingError("download.parse", "yt-dlp produced no media file")
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
    if re.search(r"sign in|cookies|login|authentication", text):
        return ProcessingError("download.login_required", "Download requires sign-in or cookies")
    if re.search(r"not available in your country|geo|region", text):
        return ProcessingError("download.geo_restricted", "Content is not available in your region")
    if re.search(r"private video|unsupported url|not a valid url|live event|is live", text):
        return ProcessingError("download.unsupported", "Unsupported video type or URL")
    if re.search(r"timed out|connection|network|temporary failure|http error", text):
        return ProcessingError("download.network", "Network error; download failed")
    return ProcessingError("download.parse", "Could not parse video info")


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
