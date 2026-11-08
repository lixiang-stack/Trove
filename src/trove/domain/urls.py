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
        raise ValidationError("链接不能为空", details={"code": "url.empty"})
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        raise ValidationError("只支持 http/https 链接", details={"code": "url.scheme"})
    if parts.username or parts.password:
        raise ValidationError("链接不能包含用户名或密码", details={"code": "url.credentials"})
    host = (parts.hostname or "").lower()
    if host in YOUTUBE_HOSTS:
        canonical = _canonical_youtube(parts, raw)
        return CanonicalVideoUrl(raw, canonical, canonical, Platform.YOUTUBE)
    if host in BILIBILI_HOSTS:
        canonical = _canonical_bilibili(parts, raw)
        return CanonicalVideoUrl(raw, canonical, canonical, Platform.BILIBILI)
    raise ValidationError(
        "只支持 B 站和 YouTube 单条视频链接",
        details={"code": "url.unsupported_platform"},
    )


def _youtube_id(parts) -> str:
    host = (parts.hostname or "").lower()
    path = parts.path.rstrip("/")
    if host == "youtu.be":
        candidate = path.lstrip("/")
        if not candidate or "/" in candidate:
            raise ValidationError("无法识别 YouTube 视频 ID", details={"code": "url.parse"})
        return candidate
    if path in {"/watch", "/watch/"}:
        query = parse_qs(parts.query)
        if any(key in query for key in PLAYLIST_PARAMS):
            raise ValidationError(
                "不支持播放列表或电台链接，请只粘贴单条视频",
                details={"code": "url.playlist_not_supported"},
            )
        values = query.get("v") or []
        if not values:
            raise ValidationError("YouTube 链接缺少视频 ID", details={"code": "url.parse"})
        return values[0]
    if path.startswith("/shorts/"):
        return path.rsplit("/", 1)[-1]
    if path.startswith("/live/"):
        raise ValidationError("不支持直播链接", details={"code": "url.live_not_supported"})
    raise ValidationError(
        "不支持的 YouTube 链接类型，请粘贴单条视频",
        details={"code": "url.unsupported_type"},
    )


def _canonical_youtube(parts, raw: str) -> str:
    video_id = _youtube_id(parts)
    if not YOUTUBE_ID_RE.match(video_id):
        raise ValidationError("YouTube 视频 ID 无效", details={"code": "url.parse"})
    return f"https://www.youtube.com/watch?v={video_id}"


def _canonical_bilibili(parts, raw: str) -> str:
    path = parts.path.rstrip("/")
    if not path.startswith("/video/"):
        if path.startswith("/live/"):
            raise ValidationError("不支持直播链接", details={"code": "url.live_not_supported"})
        raise ValidationError(
            "不支持的 B 站链接类型，请粘贴视频页链接",
            details={"code": "url.unsupported_type"},
        )
    video_id = path.removeprefix("/video/")
    if "/" in video_id or not BILIBILI_ID_RE.match(video_id):
        raise ValidationError("B 站视频 ID 无效", details={"code": "url.parse"})
    query = parse_qs(parts.query)
    if any(key in query for key in PLAYLIST_PARAMS):
        raise ValidationError(
            "不支持多 P 或播放列表链接，请只粘贴单条视频",
            details={"code": "url.playlist_not_supported"},
        )
    p_values = query.get("p") or []
    for value in p_values:
        try:
            if int(value) > 1:
                raise ValidationError(
                    "不支持多 P 链接，请只粘贴单条视频",
                    details={"code": "url.playlist_not_supported"},
                )
        except ValueError as exc:
            raise ValidationError("B 站分 P 参数无效", details={"code": "url.parse"}) from exc
    normalized_id = video_id if video_id.lower().startswith("av") else f"BV{video_id[2:]}"
    return f"https://www.bilibili.com/video/{normalized_id}"


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
        raise ValidationError("feed 必须是 http/https URL", details={"code": "feed.scheme"})
    if not parts.hostname:
        raise ValidationError("feed URL 缺少主机名", details={"code": "feed.parse"})
    if parts.username or parts.password:
        raise ValidationError("feed URL 不能包含用户名或密码", details={"code": "feed.credentials"})
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
