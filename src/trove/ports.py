from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from trove.content_package import SourceDocument

__all__ = [
    "AudioExtractor",
    "AudioResult",
    "BookChapterData",
    "BookCoverData",
    "BookExtractor",
    "BookResult",
    "DOWNLOAD_MEDIA_FILENAME",
    "DownloadResult",
    "Downloader",
    "FeedClient",
    "FeedEpisode",
    "FeedPreview",
    "OrganizationResult",
    "Organizer",
    "SearchHit",
    "SearchIndex",
    "SearchResult",
    "StageContext",
    "Transcriber",
    "TranscriptResult",
    "TranscriptSegmentData",
]


DOWNLOAD_MEDIA_FILENAME = "download.media"


@dataclass(slots=True)
class StageContext:
    item_id: str
    run_id: str
    work_dir: Path
    should_cancel: Callable[[], bool]
    log: Callable[[str], None]

    def check_cancelled(self) -> None:
        from trove.errors import ProcessingCancelled

        if self.should_cancel():
            raise ProcessingCancelled("cancelled")


@dataclass(slots=True)
class DownloadResult:
    path: Path
    title: str | None = None
    author: str | None = None
    published_at: str | None = None
    duration_sec: float | None = None
    language: str | None = None


@dataclass(slots=True)
class FeedEpisode:
    guid: str | None
    title: str
    author: str | None
    published_at: str | None
    duration_sec: float | None
    enclosure_url: str
    enclosure_type: str | None
    enclosure_size: int | None


@dataclass(slots=True)
class FeedPreview:
    title: str
    author: str | None
    link: str | None
    episodes: list[FeedEpisode] = field(default_factory=list)


@dataclass(slots=True)
class AudioResult:
    path: Path
    duration_sec: float | None
    mime: str
    extension: str


@dataclass(slots=True)
class TranscriptSegmentData:
    seq: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(slots=True)
class TranscriptResult:
    segments: list[TranscriptSegmentData]
    language: str | None = None
    model: str | None = None


@dataclass(slots=True)
class OrganizationResult:
    summary: str
    tags: list[str]
    model: str
    prompt_version: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass(slots=True)
class BookChapterData:
    chapter_index: int
    title: str
    html: str
    text: str
    paragraphs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BookCoverData:
    data: bytes
    extension: str
    mime: str


@dataclass(slots=True)
class BookResult:
    title: str
    author: str | None
    language: str | None
    chapters: list[BookChapterData]
    cover: BookCoverData | None = None


@dataclass(slots=True)
class SearchHit:
    item_id: str
    score: float
    doc_kind: str
    ref: str
    text: str


@dataclass(slots=True)
class SearchResult:
    item_id: str
    score: float
    evidence: list[SearchHit]


class Downloader(Protocol):
    def download(
        self, source: SourceDocument, context: StageContext
    ) -> DownloadResult: ...


class FeedClient(Protocol):
    def preview(self, feed_url: str) -> FeedPreview: ...


class AudioExtractor(Protocol):
    def extract(
        self,
        source: Path,
        destination: Path,
        *,
        force_transcode: bool,
        context: StageContext,
    ) -> AudioResult: ...


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path, context: StageContext) -> TranscriptResult: ...


class Organizer(Protocol):
    def organize(
        self,
        *,
        text: str,
        title: str,
        existing_tags: list[str],
        context: StageContext,
    ) -> OrganizationResult: ...


class BookExtractor(Protocol):
    def validate(self, book_path: Path) -> None: ...

    def extract(self, book_path: Path, context: StageContext) -> BookResult: ...


class SearchIndex(Protocol):
    def index_item(self, item_id: str) -> None: ...

    def delete_item(self, item_id: str) -> None: ...

    def search(self, query: str, *, limit: int = 50) -> list[SearchResult]: ...

    def rebuild(self) -> int: ...
