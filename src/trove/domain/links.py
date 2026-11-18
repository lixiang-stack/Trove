from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from trove.domain.items import Platform


class LinkKind(StrEnum):
    VIDEO = "video"
    COLLECTION = "collection"
    EBOOK = "ebook"
    PODCAST_FEED = "podcast_feed"


class LinkTarget(StrEnum):
    VIDEO = "video"
    VIDEO_PAGE = "video_page"
    COLLECTION = "collection"
    EBOOK = "ebook"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LinkCandidate:
    raw: str
    canonical: str
    target: LinkTarget
    platform: Platform | None = None
    ignored_playlist: bool = False
    title_hint: str | None = None


@dataclass(frozen=True, slots=True)
class InspectedEpisode:
    title: str
    canonical_url: str
    source_key: str
    index: int
    duration_sec: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.canonical_url,
            "source_key": self.source_key,
            "index": self.index,
            "duration_sec": self.duration_sec,
        }


@dataclass(slots=True)
class LinkInspection:
    kind: LinkKind
    raw_url: str
    canonical_url: str
    title: str
    platform: Platform
    author: str | None = None
    duration_sec: float | None = None
    episode_count: int = 0
    total_duration_sec: float | None = None
    file_size: int | None = None
    content_type: str | None = None
    episodes: list[InspectedEpisode] = field(default_factory=list)
    feed: dict[str, Any] | None = None
    existing_collection_id: str | None = None
    existing_episode_count: int = 0
    upstream_removed_count: int = 0
    conflict_count: int = 0
    attachable_count: int = 0
    deduplicated: bool = False
    ignored_playlist: bool = False
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self, *, preview_limit: int = 10) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "raw_url": self.raw_url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "author": self.author,
            "platform": str(self.platform),
            "duration_sec": self.duration_sec,
            "episode_count": self.episode_count,
            "total_duration_sec": self.total_duration_sec,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "episodes": [
                episode.to_dict() for episode in self.episodes[:preview_limit]
            ],
            "feed": self.feed,
            "existing_collection_id": self.existing_collection_id,
            "existing_episode_count": self.existing_episode_count,
            "upstream_removed_count": self.upstream_removed_count,
            "conflict_count": self.conflict_count,
            "attachable_count": self.attachable_count,
            "deduplicated": self.deduplicated,
            "ignored_playlist": self.ignored_playlist,
            "warnings": self.warnings,
        }
