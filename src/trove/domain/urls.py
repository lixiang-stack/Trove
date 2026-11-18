from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from trove.domain.items import Platform, SourceType
from trove.domain.links import LinkCandidate, LinkTarget
from trove.errors import ValidationError

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
BILIBILI_HOSTS = {"bilibili.com", "www.bilibili.com", "m.bilibili.com"}
BILIBILI_SPACE_HOSTS = {"space.bilibili.com"}

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
YOUTUBE_PLAYLIST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,128}$")
BILIBILI_ID_RE = re.compile(r"^(BV[0-9A-Za-z]{10}|av\d+)$", re.IGNORECASE)
BILIBILI_MID_RE = re.compile(r"^\d+$")
BILIBILI_SID_RE = re.compile(r"^\d+$")
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


def classify_link_url(raw: str) -> LinkCandidate:
    raw = (raw or "").strip()
    if not raw:
        raise ValidationError("URL cannot be empty", details={"code": "link.empty"})
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        raise ValidationError(
            "Only http/https URLs are supported", details={"code": "link.scheme"}
        )
    if parts.username or parts.password:
        raise ValidationError(
            "URL must not contain a username or password",
            details={"code": "link.credentials"},
        )
    host = (parts.hostname or "").lower()
    if host in YOUTUBE_HOSTS:
        return _classify_youtube(raw, parts)
    if host in BILIBILI_SPACE_HOSTS:
        return _classify_bilibili_space(raw, parts)
    if host in BILIBILI_HOSTS:
        return _classify_bilibili(raw, parts)
    canonical = canonicalize_epub_url(raw)
    if Path(urlsplit(canonical).path).suffix.lower() == ".epub":
        return LinkCandidate(
            raw=raw,
            canonical=canonical,
            target=LinkTarget.EBOOK,
            platform=Platform.WEB,
            title_hint=epub_title_hint(canonical),
        )
    return LinkCandidate(raw=raw, canonical=canonical, target=LinkTarget.UNKNOWN)


def _classify_youtube(raw: str, parts) -> LinkCandidate:
    path = parts.path.rstrip("/")
    query = parse_qs(parts.query)
    if path == "/playlist":
        playlist_url = canonicalize_youtube_playlist_url(raw)
        return LinkCandidate(
            raw=raw,
            canonical=playlist_url,
            target=LinkTarget.COLLECTION,
            platform=Platform.YOUTUBE,
        )
    if path == "/watch":
        if not query.get("v"):
            raise ValidationError(
                "YouTube URL is missing a video ID", details={"code": "url.parse"}
            )
        ignored = any(key in query for key in PLAYLIST_PARAMS)
        cleaned = _without_query_keys(parts, PLAYLIST_PARAMS)
        video = canonicalize_video_url(cleaned)
        return LinkCandidate(
            raw=raw,
            canonical=video.canonical,
            target=LinkTarget.VIDEO,
            platform=Platform.YOUTUBE,
            ignored_playlist=ignored,
        )
    if path.startswith("/live/"):
        raise ValidationError(
            "Live URLs are not supported", details={"code": "link.live_not_supported"}
        )
    if path.startswith("/shorts/") or (parts.hostname or "").lower() == "youtu.be":
        video = canonicalize_video_url(raw)
        return LinkCandidate(
            raw=raw,
            canonical=video.canonical,
            target=LinkTarget.VIDEO,
            platform=Platform.YOUTUBE,
        )
    raise ValidationError(
        "Unsupported YouTube URL type; paste a video or playlist URL",
        details={"code": "link.unsupported"},
    )


def _classify_bilibili(raw: str, parts) -> LinkCandidate:
    path = parts.path.rstrip("/")
    query = parse_qs(parts.query)
    if path.startswith("/live/"):
        raise ValidationError(
            "Live URLs are not supported", details={"code": "link.live_not_supported"}
        )
    if not path.startswith("/video/"):
        raise ValidationError(
            "Unsupported Bilibili URL type; paste a video or collection URL",
            details={"code": "link.unsupported"},
        )
    if any(key in query for key in PLAYLIST_PARAMS):
        raise ValidationError(
            "Bilibili playlist parameters are not supported; paste the video or collection page",
            details={"code": "link.unsupported"},
        )
    canonical = canonicalize_video_url(raw)
    target = LinkTarget.VIDEO if "p" in query else LinkTarget.VIDEO_PAGE
    return LinkCandidate(
        raw=raw,
        canonical=canonical.canonical,
        target=target,
        platform=Platform.BILIBILI,
    )


def _classify_bilibili_space(raw: str, parts) -> LinkCandidate:
    path = parts.path.rstrip("/")
    query = parse_qs(parts.query)
    match = re.fullmatch(r"/(\d+)/channel/(collectiondetail|seriesdetail)", path)
    if not match:
        raise ValidationError(
            "Only Bilibili collection and series pages are supported",
            details={"code": "link.unsupported"},
        )
    mid, kind = match.groups()
    sid_values = query.get("sid") or []
    sid = sid_values[0] if sid_values else ""
    if not BILIBILI_MID_RE.match(mid) or not BILIBILI_SID_RE.match(sid):
        raise ValidationError(
            "Invalid Bilibili collection URL", details={"code": "url.parse"}
        )
    canonical = f"https://space.bilibili.com/{mid}/channel/{kind}?sid={sid}"
    return LinkCandidate(
        raw=raw,
        canonical=canonical,
        target=LinkTarget.COLLECTION,
        platform=Platform.BILIBILI,
    )


def canonicalize_youtube_playlist_url(raw: str) -> str:
    parts = urlsplit((raw or "").strip())
    if parts.scheme not in {"http", "https"}:
        raise ValidationError(
            "Only http/https URLs are supported", details={"code": "link.scheme"}
        )
    if parts.username or parts.password:
        raise ValidationError(
            "URL must not contain a username or password",
            details={"code": "link.credentials"},
        )
    host = (parts.hostname or "").lower()
    if host not in YOUTUBE_HOSTS or parts.path.rstrip("/") != "/playlist":
        raise ValidationError(
            "Unsupported YouTube playlist URL", details={"code": "link.unsupported"}
        )
    values = parse_qs(parts.query).get("list") or []
    playlist_id = values[0] if values else ""
    if not YOUTUBE_PLAYLIST_ID_RE.match(playlist_id):
        raise ValidationError(
            "YouTube playlist URL is missing a valid list ID",
            details={"code": "url.parse"},
        )
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def canonicalize_epub_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValidationError("URL cannot be empty", details={"code": "link.empty"})
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"}:
        raise ValidationError(
            "Only http/https URLs are supported", details={"code": "link.scheme"}
        )
    if not parts.hostname:
        raise ValidationError(
            "URL is missing a hostname", details={"code": "link.unsupported"}
        )
    if parts.username or parts.password:
        raise ValidationError(
            "URL must not contain a username or password",
            details={"code": "link.credentials"},
        )
    return parts._replace(fragment="").geturl()


def epub_title_hint(url: str) -> str:
    name = unquote(Path(urlsplit(url).path).name)
    if name.lower().endswith(".epub"):
        name = name[:-5]
    return name.strip() or "Untitled book"


def _without_query_keys(parts, keys: set[str]) -> str:
    query = [
        (key, value)
        for key, values in parse_qs(parts.query, keep_blank_values=True).items()
        for value in values
        if key not in keys
    ]
    return parts._replace(query=urlencode(query), fragment="").geturl()


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
