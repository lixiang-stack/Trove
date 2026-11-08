from __future__ import annotations

import calendar
from datetime import UTC, datetime

import feedparser

from trove.adapters.safe_http import SafeHttpClient, SafeHttpError
from trove.errors import ProcessingError, ValidationError
from trove.ports import FeedEpisode, FeedPreview


class PodcastFeedClient:
    def __init__(self, http: SafeHttpClient, *, max_bytes: int) -> None:
        self.http = http
        self.max_bytes = max_bytes

    def preview(self, feed_url: str) -> FeedPreview:
        try:
            response = self.http.get_bytes(feed_url, max_bytes=self.max_bytes)
        except SafeHttpError as exc:
            raise ValidationError(exc.message, details={"code": exc.code}) from exc
        parsed = feedparser.parse(response.content)
        if parsed.bozo and not parsed.entries:
            raise ValidationError("feed 解析失败", details={"code": "feed.parse"})
        feed = parsed.feed
        episodes: list[FeedEpisode] = []
        for entry in parsed.entries[:50]:
            enclosure = _enclosure(entry)
            if enclosure is None:
                continue
            episodes.append(
                FeedEpisode(
                    guid=_guid(entry),
                    title=str(entry.get("title") or "未命名单集"),
                    author=str(entry.get("author") or feed.get("author") or "") or None,
                    published_at=_published(entry),
                    duration_sec=_duration(entry),
                    enclosure_url=enclosure[0],
                    enclosure_type=enclosure[1],
                    enclosure_size=enclosure[2],
                )
            )
        return FeedPreview(
            title=str(feed.get("title") or "播客"),
            author=str(feed.get("author") or "") or None,
            link=str(feed.get("link") or "") or None,
            episodes=episodes,
        )


def _enclosure(entry) -> tuple[str, str | None, int | None] | None:
    for enclosure in entry.get("enclosures", []):
        href = enclosure.get("href") or enclosure.get("url")
        if not href:
            continue
        size = enclosure.get("length")
        try:
            parsed_size = int(size) if size is not None else None
        except (TypeError, ValueError):
            parsed_size = None
        return str(href), enclosure.get("type"), parsed_size
    return None


def _guid(entry) -> str | None:
    value = entry.get("id") or entry.get("guid")
    return str(value) if value else None


def _published(entry) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC).isoformat()
    value = entry.get("published") or entry.get("updated")
    return str(value) if value else None


def _duration(entry) -> float | None:
    value = entry.get("itunes_duration")
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        if ":" in text:
            seconds = 0
            for part in text.split(":"):
                seconds = seconds * 60 + int(part)
            return float(seconds)
        return float(text)
    except ValueError:
        return None


def feed_episode(preview: FeedPreview, guid: str | None) -> FeedEpisode:
    for episode in preview.episodes:
        if episode.guid == guid:
            return episode
    if guid:
        raise ValidationError("feed 中找不到该单集", details={"code": "feed.episode_not_found"})
    raise ValidationError("缺少单集标识", details={"code": "feed.episode_not_found"})


def download_episode(
    http: SafeHttpClient,
    episode: FeedEpisode,
    destination,
    *,
    max_bytes: int,
) -> None:
    try:
        http.download_to_file(
            episode.enclosure_url,
            destination,
            max_bytes=max_bytes,
            allowed_types={
                "audio/mpeg",
                "audio/mp4",
                "audio/aac",
                "audio/x-m4a",
                "audio/ogg",
                "audio/opus",
                "application/octet-stream",
            },
        )
    except SafeHttpError as exc:
        code = exc.code
        if not code.startswith("download."):
            code = "download.network"
        raise ProcessingError(code, exc.message) from exc
