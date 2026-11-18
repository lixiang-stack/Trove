from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from trove.config import Config
from trove.errors import ProcessingError
from trove.ports import VideoEntry, VideoInfo

INSPECT_TIMEOUT_SECONDS = 25.0


class YtDlpVideoInspector:
    """Read collection metadata with yt-dlp without downloading media."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def inspect(self, url: str, *, playlist: bool) -> VideoInfo:
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--flat-playlist",
            "-J",
            "--no-warnings",
            "--skip-download",
            "--no-progress",
            "--playlist-end",
            str(self.config.max_collection_items + 1),
        ]
        if not playlist:
            command.append("--no-playlist")
        if self.config.ytdlp_cookies and self.config.ytdlp_cookies.exists():
            command.extend(["--cookies", str(self.config.ytdlp_cookies)])
        command.append(url)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=INSPECT_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProcessingError(
                "inspect.timeout", "Link inspection timed out"
            ) from exc
        except OSError as exc:
            raise ProcessingError(
                "inspect.failed", f"Could not run yt-dlp: {exc}"
            ) from exc
        if result.returncode != 0:
            raise _classify_error(result.stderr)
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProcessingError(
                "inspect.failed", "yt-dlp returned invalid metadata"
            ) from exc
        return _parse_info(data)


def _parse_info(data: dict[str, Any]) -> VideoInfo:
    entries_value = data.get("entries")
    entries = entries_value if isinstance(entries_value, list) else []
    is_playlist = data.get("_type") == "playlist" or bool(entries)
    title = _string(data.get("title"))
    author = _string(data.get("uploader") or data.get("channel"))
    duration = _float(data.get("duration"))
    if not is_playlist:
        return VideoInfo(
            is_playlist=False,
            title=title,
            author=author,
            duration_sec=duration,
            entries=[],
        )
    parsed: list[VideoEntry] = []
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        entry_url = _entry_url(entry)
        if not entry_url:
            continue
        index = _int(entry.get("playlist_index")) or position
        parsed.append(
            VideoEntry(
                title=_string(entry.get("title")) or f"Episode {index}",
                url=entry_url,
                index=index,
                duration_sec=_float(entry.get("duration")),
            )
        )
    return VideoInfo(
        is_playlist=True,
        title=title,
        author=author,
        duration_sec=duration,
        entries=parsed,
    )


def _entry_url(entry: dict[str, Any]) -> str | None:
    for key in ("webpage_url", "url"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    video_id = entry.get("id")
    if not isinstance(video_id, str) or not video_id:
        return None
    ie_key = str(entry.get("ie_key") or entry.get("extractor_key") or "")
    if "youtube" in ie_key.lower():
        return f"https://www.youtube.com/watch?v={video_id}"
    if "bilibili" in ie_key.lower():
        return f"https://www.bilibili.com/video/{video_id}"
    return None


def _classify_error(stderr: str) -> ProcessingError:
    lowered = stderr.lower()
    if any(token in lowered for token in ("login", "sign in", "cookies", "authentication")):
        return ProcessingError("download.login_required", "Sign-in is required")
    if any(token in lowered for token in ("not available in your country", "geo", "region")):
        return ProcessingError("download.geo_restricted", "Content is region-restricted")
    if "unsupported url" in lowered:
        return ProcessingError("link.unsupported", "This link type is not supported")
    return ProcessingError("inspect.failed", "Could not inspect the link metadata")


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
