from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit

from trove.domain.items import Platform, SourceType
from trove.errors import ValidationError

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
BILIBILI_HOSTS = {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
BILIBILI_ID_RE = re.compile(r"^(BV[0-9A-Za-z]{10}|av\d+)$", re.IGNORECASE)
PLAYLIST_PARAMS = {"list", "start_radio", "index", "playnext"}


@dataclass(frozen=True, slots=True)
class CanonicalVideoUrl:
    raw: str
    canonical: str
    source_key: str
    platform: Platform
    source_type: SourceType = SourceType.VIDEO_URL


def canonicalize_video_url(raw: str) -> CanonicalVideoUrl:
    raw = (raw or "").strip()
    if not raw:
        raise ValidationError("URL cannot be empty", details={"code": "url.empty"})
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        raise ValidationError("Only http/https URLs are supported", details={"code": "url.scheme"})
    if parts.username or parts.password:
        raise ValidationError(
            "URL must not contain a username or password", details={"code": "url.credentials"}
        )
    host = (parts.hostname or "").lower()
    if host in YOUTUBE_HOSTS:
        canonical = _canonical_youtube(parts)
        return CanonicalVideoUrl(raw, canonical, canonical, Platform.YOUTUBE)
    if host in BILIBILI_HOSTS:
        canonical = _canonical_bilibili(parts)
        return CanonicalVideoUrl(raw, canonical, canonical, Platform.BILIBILI)
    raise ValidationError(
        "Only single-video Bilibili and YouTube URLs are supported",
        details={"code": "url.unsupported_platform"},
    )


def _youtube_id(parts) -> str:
    host = (parts.hostname or "").lower()
    path = parts.path.rstrip("/")
    if host == "youtu.be":
        candidate = path.lstrip("/")
        if not candidate or "/" in candidate:
            raise ValidationError(
                "Could not recognize YouTube video ID", details={"code": "url.parse"}
            )
        return candidate
    if path in {"/watch", "/watch/"}:
        query = parse_qs(parts.query)
        if any(key in query for key in PLAYLIST_PARAMS):
            raise ValidationError(
                "Playlists and radio URLs are not supported; paste a single video",
                details={"code": "url.playlist_not_supported"},
            )
        values = query.get("v") or []
        if not values:
            raise ValidationError(
                "YouTube URL is missing a video ID", details={"code": "url.parse"}
            )
        return values[0]
    if path.startswith("/shorts/"):
        return path.rsplit("/", 1)[-1]
    if path.startswith("/live/"):
        raise ValidationError(
            "Live URLs are not supported", details={"code": "url.live_not_supported"}
        )
    raise ValidationError(
        "Unsupported YouTube URL type; paste a single video",
        details={"code": "url.unsupported_type"},
    )


def _canonical_youtube(parts) -> str:
    video_id = _youtube_id(parts)
    if not YOUTUBE_ID_RE.match(video_id):
        raise ValidationError("Invalid YouTube video ID", details={"code": "url.parse"})
    return f"https://www.youtube.com/watch?v={video_id}"


def _canonical_bilibili(parts) -> str:
    path = parts.path.rstrip("/")
    if not path.startswith("/video/"):
        if path.startswith("/live/"):
            raise ValidationError(
                "Live URLs are not supported", details={"code": "url.live_not_supported"}
            )
        raise ValidationError(
            "Unsupported Bilibili URL type; paste a video page URL",
            details={"code": "url.unsupported_type"},
        )
    video_id = path.removeprefix("/video/")
    if "/" in video_id or not BILIBILI_ID_RE.match(video_id):
        raise ValidationError("Invalid Bilibili video ID", details={"code": "url.parse"})
    query = parse_qs(parts.query)
    if any(key in query for key in PLAYLIST_PARAMS):
        raise ValidationError(
            "Playlist URLs are not supported; paste a single video",
            details={"code": "url.playlist_not_supported"},
        )
    part = 1
    p_values = query.get("p") or []
    if p_values:
        try:
            part = int(p_values[0])
        except ValueError as exc:
            raise ValidationError(
                "Invalid Bilibili part parameter", details={"code": "url.parse"}
            ) from exc
        if part < 1:
            raise ValidationError("Invalid Bilibili part parameter", details={"code": "url.parse"})
    normalized_id = video_id if video_id.lower().startswith("av") else f"BV{video_id[2:]}"
    canonical = f"https://www.bilibili.com/video/{normalized_id}"
    if part > 1:
        canonical += f"?p={part}"
    return canonical


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "spm_id_from",
    "vd_source",
}


def canonicalize_feed_url(raw: str) -> str:
    raw = (raw or "").strip()
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        raise ValidationError("Feed must be an http/https URL", details={"code": "feed.scheme"})
    if not parts.hostname:
        raise ValidationError("Feed URL is missing a hostname", details={"code": "feed.parse"})
    if parts.username or parts.password:
        raise ValidationError(
            "Feed URL must not contain a username or password", details={"code": "feed.credentials"}
        )
    query = [
        (key, value)
        for key, values in parse_qs(parts.query, keep_blank_values=True).items()
        for value in values
        if key not in TRACKING_PARAMS
    ]
    return parts._replace(query=urlencode(query), fragment="").geturl()


def podcast_source_key(feed_url: str, guid: str | None, enclosure_url: str) -> str:
    identity = guid or enclosure_url
    return f"{canonicalize_feed_url(feed_url)}#{identity}"
