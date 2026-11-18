from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from trove.adapters.safe_http import SafeHttpError
from trove.domain.items import Platform
from trove.domain.links import (
    InspectedEpisode,
    LinkCandidate,
    LinkInspection,
    LinkKind,
    LinkTarget,
)
from trove.domain.urls import (
    canonicalize_epub_url,
    canonicalize_feed_url,
    canonicalize_video_url,
    classify_link_url,
    epub_title_hint,
)
from trove.errors import ProcessingError, ValidationError
from trove.ports import (
    FeedClient,
    FeedPreview,
    LinkProbe,
    LinkProbeResult,
    VideoInfo,
    VideoInspector,
)
from trove.services.collections import CollectionService
from trove.services.library import LibraryService


class InspectService:
    def __init__(
        self,
        config,
        library: LibraryService,
        collections: CollectionService,
        feed_client: FeedClient,
        video_inspector: VideoInspector,
        link_probe: LinkProbe,
    ) -> None:
        self.config = config
        self.library = library
        self.collections = collections
        self.feed_client = feed_client
        self.video_inspector = video_inspector
        self.link_probe = link_probe

    def inspect(self, raw_url: str) -> LinkInspection:
        candidate = classify_link_url(raw_url)
        try:
            if candidate.target == LinkTarget.EBOOK:
                return self._inspect_ebook(candidate, canonical=candidate.canonical)
            if candidate.target == LinkTarget.UNKNOWN:
                return self._inspect_unknown(candidate)
            return self._inspect_video(candidate)
        except ProcessingError as exc:
            raise ValidationError(exc.message, details={"code": exc.code}) from exc
        except SafeHttpError as exc:
            code = exc.code if exc.code.startswith("ebook.") else "ebook.not_found"
            raise ValidationError(exc.message, details={"code": code}) from exc

    # ------------------------------------------------------------------
    # Video / collection
    # ------------------------------------------------------------------
    def _inspect_video(self, candidate: LinkCandidate) -> LinkInspection:
        playlist = candidate.target in {LinkTarget.COLLECTION, LinkTarget.VIDEO_PAGE}
        info = self.video_inspector.inspect(candidate.canonical, playlist=playlist)
        if candidate.target == LinkTarget.VIDEO:
            return self._single(candidate, info)
        if candidate.target == LinkTarget.VIDEO_PAGE:
            if info.is_playlist and len(info.entries) > 1:
                return self._collection(candidate, info)
            return self._single(candidate, info)
        return self._collection(candidate, info)

    def _single(self, candidate: LinkCandidate, info: VideoInfo) -> LinkInspection:
        platform = candidate.platform or Platform.WEB
        existing = self.library.find_by_source_key(candidate.canonical)
        warnings = []
        if candidate.ignored_playlist:
            warnings.append(
                {
                    "code": "link.ignored_playlist",
                    "message": "链接里的播放列表参数已忽略，只添加当前视频。",
                }
            )
        return LinkInspection(
            kind=LinkKind.VIDEO,
            raw_url=candidate.raw,
            canonical_url=candidate.canonical,
            title=info.title or candidate.canonical,
            author=info.author,
            platform=platform,
            duration_sec=info.duration_sec,
            episode_count=1,
            total_duration_sec=info.duration_sec,
            deduplicated=existing is not None,
            ignored_playlist=candidate.ignored_playlist,
            warnings=warnings,
        )

    def _collection(
        self, candidate: LinkCandidate, info: VideoInfo
    ) -> LinkInspection:
        warnings: list[dict[str, Any]] = []
        episodes = self._collection_episodes(info, warnings)
        total_duration = self._validate_collection(episodes)
        existing = self.collections.find_by_source_key(candidate.canonical)
        existing_keys = (
            {item.item.source_key for item in existing.items} if existing else set()
        )
        incoming_keys = {episode.source_key for episode in episodes}
        upstream_removed = len(existing_keys - incoming_keys)
        attachable, conflicts = self._collection_membership(episodes, existing)
        warnings.extend(
            self._collection_warnings(upstream_removed, attachable, conflicts)
        )
        return LinkInspection(
            kind=LinkKind.COLLECTION,
            raw_url=candidate.raw,
            canonical_url=candidate.canonical,
            title=info.title or "Video collection",
            author=info.author,
            platform=candidate.platform or Platform.WEB,
            episode_count=len(episodes),
            total_duration_sec=total_duration,
            episodes=episodes,
            existing_collection_id=existing.collection.id if existing else None,
            existing_episode_count=len(existing.items) if existing else 0,
            upstream_removed_count=upstream_removed,
            conflict_count=conflicts,
            attachable_count=attachable,
            warnings=warnings,
        )

    def _collection_episodes(
        self, info: VideoInfo, warnings: list[dict[str, Any]]
    ) -> list[InspectedEpisode]:
        episodes: list[InspectedEpisode] = []
        seen: set[str] = set()
        for entry in info.entries:
            try:
                canonical = canonicalize_video_url(entry.url)
            except ValidationError:
                warnings.append(
                    {
                        "code": "collection.episode_invalid",
                        "message": f"跳过无法识别的单集：{entry.title}",
                    }
                )
                continue
            if canonical.source_key in seen:
                continue
            seen.add(canonical.source_key)
            episodes.append(
                InspectedEpisode(
                    title=entry.title,
                    canonical_url=canonical.canonical,
                    source_key=canonical.source_key,
                    index=entry.index,
                    duration_sec=entry.duration_sec,
                )
            )
        if not episodes:
            raise ValidationError(
                "Collection has no downloadable episodes",
                details={"code": "collection.empty"},
            )
        return episodes

    def _validate_collection(
        self, episodes: list[InspectedEpisode]
    ) -> float | None:
        if len(episodes) > self.config.max_collection_items:
            raise ValidationError(
                f"Collection has {len(episodes)} episodes; limit is "
                f"{self.config.max_collection_items}",
                details={"code": "collection.too_large"},
            )
        durations = [episode.duration_sec for episode in episodes]
        known_total = sum(duration for duration in durations if duration is not None)
        if known_total > self.config.max_collection_duration_sec:
            raise ValidationError(
                "Collection exceeds the duration limit",
                details={"code": "collection.too_large"},
            )
        if all(duration is not None for duration in durations):
            return float(known_total)
        return None

    def _collection_membership(
        self, episodes: list[InspectedEpisode], existing
    ) -> tuple[int, int]:
        attachable = 0
        conflicts = 0
        existing_id = existing.collection.id if existing else None
        for episode in episodes:
            item = self.library.find_by_source_key(episode.source_key)
            if item is None:
                continue
            if item.item.collection_id is None:
                attachable += 1
            elif item.item.collection_id != existing_id:
                conflicts += 1
        return attachable, conflicts

    @staticmethod
    def _collection_warnings(
        upstream_removed: int, attachable: int, conflicts: int
    ) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        if upstream_removed:
            warnings.append(
                {
                    "code": "collection.upstream_removed",
                    "message": (
                        f"上游已移除 {upstream_removed} 集；本地会保留，不自动删除。"
                    ),
                    "count": upstream_removed,
                }
            )
        if attachable:
            warnings.append(
                {
                    "code": "collection.episode_attach",
                    "message": (
                        f"{attachable} 集已在库中，将并入合集并保留已有进度。"
                    ),
                    "count": attachable,
                }
            )
        if conflicts:
            warnings.append(
                {
                    "code": "collection.episode_conflict",
                    "message": f"{conflicts} 集已属于其他合集，将跳过。",
                    "count": conflicts,
                }
            )
        return warnings

    # ------------------------------------------------------------------
    # EPUB / feed / unknown
    # ------------------------------------------------------------------
    def _inspect_ebook(
        self, candidate: LinkCandidate, *, canonical: str
    ) -> LinkInspection:
        probe = self.link_probe.head(canonical)
        return self._ebook_from_probe(candidate, canonical, probe)

    def _ebook_from_probe(
        self, candidate: LinkCandidate, canonical: str, probe: LinkProbeResult
    ) -> LinkInspection:
        final_url = canonicalize_epub_url(probe.final_url or canonical)
        content_type = (probe.content_type or "").split(";")[0].lower()
        if content_type in {"text/html", "application/xhtml+xml"}:
            raise ValidationError(
                "Link points to an HTML page, not an EPUB file",
                details={"code": "ebook.invalid_type"},
            )
        if content_type and content_type not in {
            "application/epub+zip",
            "application/zip",
            "application/octet-stream",
            "binary/octet-stream",
        }:
            raise ValidationError(
                f"Unsupported EPUB content type: {content_type}",
                details={"code": "ebook.invalid_type"},
            )
        if (
            probe.content_length is not None
            and probe.content_length > self.config.max_epub_bytes
        ):
            raise ValidationError(
                "EPUB exceeds the size limit",
                details={"code": "ebook.too_large"},
            )
        existing = self.library.find_by_source_key(final_url)
        return LinkInspection(
            kind=LinkKind.EBOOK,
            raw_url=candidate.raw,
            canonical_url=final_url,
            title=epub_title_hint(final_url),
            platform=Platform.WEB,
            file_size=probe.content_length,
            content_type=probe.content_type,
            deduplicated=existing is not None,
        )

    def _inspect_unknown(self, candidate: LinkCandidate) -> LinkInspection:
        suffix = Path(urlsplit(candidate.canonical).path).suffix.lower()
        if suffix in {".xml", ".rss", ".atom"}:
            return self._inspect_feed(candidate)
        try:
            probe = self.link_probe.head(candidate.canonical)
        except SafeHttpError:
            try:
                return self._inspect_feed(candidate)
            except ValidationError as exc:
                raise ValidationError(
                    "This link type is not supported",
                    details={"code": "link.unsupported"},
                ) from exc
        content_type = (probe.content_type or "").split(";")[0].lower()
        if content_type == "application/epub+zip":
            return self._ebook_from_probe(candidate, candidate.canonical, probe)
        if content_type in {
            "application/rss+xml",
            "application/atom+xml",
            "application/xml",
            "text/xml",
        }:
            return self._inspect_feed(candidate)
        if content_type in {"text/html", "application/xhtml+xml"}:
            raise ValidationError(
                "Only direct EPUB files, video links, and podcast feeds are supported",
                details={"code": "link.unsupported"},
            )
        if content_type and content_type not in {
            "application/octet-stream",
            "binary/octet-stream",
        }:
            raise ValidationError(
                f"Unsupported link content type: {content_type}",
                details={"code": "link.unsupported"},
            )
        try:
            return self._inspect_feed(candidate)
        except ValidationError as exc:
            raise ValidationError(
                "This link type is not supported",
                details={"code": "link.unsupported"},
            ) from exc

    def _inspect_feed(self, candidate: LinkCandidate) -> LinkInspection:
        canonical = canonicalize_feed_url(candidate.canonical)
        feed = self.feed_client.preview(canonical)
        return LinkInspection(
            kind=LinkKind.PODCAST_FEED,
            raw_url=candidate.raw,
            canonical_url=canonical,
            title=feed.title,
            author=feed.author,
            platform=Platform.PODCAST,
            feed=_feed_dict(feed),
        )


def _feed_dict(feed: FeedPreview) -> dict[str, Any]:
    return {
        "title": feed.title,
        "author": feed.author,
        "link": feed.link,
        "episodes": [
            {
                "guid": episode.guid,
                "title": episode.title,
                "author": episode.author,
                "published_at": episode.published_at,
                "duration_sec": episode.duration_sec,
                "enclosure_url": episode.enclosure_url,
                "enclosure_type": episode.enclosure_type,
                "enclosure_size": episode.enclosure_size,
            }
            for episode in feed.episodes
        ],
    }
