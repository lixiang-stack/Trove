from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

from trove.adapters.epub import EpubExtractor
from trove.adapters.feed import PodcastFeedClient
from trove.adapters.ffmpeg import FfmpegAudioExtractor
from trove.adapters.safe_http import HttpResponse, SafeHttpError
from trove.composition import Ports
from trove.content_package import SourceDocument
from trove.domain.items import SourceType
from trove.errors import ProcessingCancelled, ProcessingError
from trove.ports import (
    DOWNLOAD_MEDIA_FILENAME,
    AudioResult,
    BookResult,
    DownloadResult,
    FeedClient,
    FeedPreview,
    LinkProbeResult,
    OrganizationResult,
    StageContext,
    TranscriptResult,
    TranscriptSegmentData,
    VideoEntry,
    VideoInfo,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class FakeHttp:
    def __init__(self, content: bytes | None = None) -> None:
        self.content = content if content is not None else (FIXTURES / "podcast.xml").read_bytes()
        self.urls: list[str] = []
        self.error: SafeHttpError | None = None

    def get_bytes(self, url: str, *, max_bytes: int) -> HttpResponse:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        if len(self.content) > max_bytes:
            raise SafeHttpError("feed.too_large", "feed too large")
        return HttpResponse(
            content=self.content,
            content_type="application/rss+xml",
            final_url=url,
        )


def make_feed_client(http: FakeHttp | None = None) -> FeedClient:
    return PodcastFeedClient(http or FakeHttp(), max_bytes=10 * 1024 * 1024)


class FakeLinkProbe:
    def __init__(self) -> None:
        self.responses: dict[str, LinkProbeResult] = {}
        self.default: LinkProbeResult | None = None
        self.error: SafeHttpError | None = None
        self.urls: list[str] = []

    def head(self, url: str) -> LinkProbeResult:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        if url in self.responses:
            return self.responses[url]
        if self.default is not None:
            return self.default
        raise SafeHttpError("ebook.not_found", "fake link probe has no response")


class FakeVideoInspector:
    def __init__(self) -> None:
        self.singles: dict[str, VideoInfo] = {}
        self.collections: dict[str, VideoInfo] = {}
        self.default_single = VideoInfo(
            is_playlist=False,
            title="Fixture Video",
            author="Fixture Author",
            duration_sec=2.0,
        )
        self.calls: list[tuple[str, bool]] = []

    def inspect(self, url: str, *, playlist: bool) -> VideoInfo:
        self.calls.append((url, playlist))
        if playlist and url in self.collections:
            return self.collections[url]
        if not playlist and url in self.singles:
            return self.singles[url]
        return self.default_single


def video_collection(
    title: str,
    entries: list[tuple[str, str, float | None]],
    *,
    author: str = "Fixture Channel",
) -> VideoInfo:
    return VideoInfo(
        is_playlist=True,
        title=title,
        author=author,
        duration_sec=None,
        entries=[
            VideoEntry(title=entry_title, url=url, index=index, duration_sec=duration)
            for index, (entry_title, url, duration) in enumerate(entries, start=1)
        ],
    )


class FakeDownloader:
    """Copy fixtures without network.

    Video titles are replaced with "Fixture Video"; browser tests that assert
    static UI should use the no-worker ``api_host`` fixture, or assert stable
    fields such as row counts and collection titles.
    """

    def __init__(self, fixture: Path | None = None, epub_fixture: Path | None = None) -> None:
        self.fixture = fixture or FIXTURES / "short.wav"
        self.epub_fixture = epub_fixture or FIXTURES / "aesop.epub"
        self.calls: list[dict] = []
        self.fail_code: str | None = None
        self.started = threading.Event()
        self.block = threading.Event()
        self.blocked = False

    def download(self, source: SourceDocument, context: StageContext) -> DownloadResult:
        self.calls.append(source)
        self.started.set()
        if self.blocked:
            self.block.clear()
            while not self.block.wait(0.02):
                if context.should_cancel():
                    raise ProcessingCancelled("cancelled")
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake download failure")
        if source.source_type == SourceType.EPUB_URL:
            destination = context.work_dir / "source.epub"
            shutil.copyfile(self.epub_fixture, destination)
            return DownloadResult(path=destination, title=source.title or "Fixture Book")
        destination = context.work_dir / DOWNLOAD_MEDIA_FILENAME
        shutil.copyfile(self.fixture, destination)
        title = (
            source.title
            if source.source_type == SourceType.PODCAST_EPISODE
            else "Fixture Video"
        )
        return DownloadResult(
            path=destination,
            title=title or "Fixture Video",
            author="Fixture Author",
            published_at="2026-11-01T00:00:00+00:00",
            duration_sec=2.0,
            language="en",
        )


class FakeTranscriber:
    def __init__(self, transcript_path: Path | None = None) -> None:
        self.data = json.loads(
            (transcript_path or FIXTURES / "transcript.json").read_text(encoding="utf-8")
        )
        self.calls: list[Path] = []
        self.fail_code: str | None = None
        self.started = threading.Event()
        self.block = threading.Event()
        self.blocked = False

    def transcribe(self, audio_path: Path, context: StageContext) -> TranscriptResult:
        self.calls.append(audio_path)
        self.started.set()
        if self.blocked:
            self.block.clear()
            while not self.block.wait(0.02):
                if context.should_cancel():
                    raise ProcessingCancelled("cancelled")
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake transcription failure")
        return TranscriptResult(
            segments=[
                TranscriptSegmentData(
                    seq=segment["seq"],
                    start_ms=segment["start_ms"],
                    end_ms=segment["end_ms"],
                    text=segment["text"],
                )
                for segment in self.data["segments"]
            ],
            language=self.data.get("language"),
            model="fake-whisper",
        )


class FakeOrganizer:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.collection_calls: list[tuple[str | None, int | None, bool]] = []
        self.existing_tags_calls: list[list[str]] = []
        self.fail_code: str | None = None
        self.summary = "这是一段关于记忆与智能体的讨论。"
        self.tags = ["智能体", "记忆", "LLM"]
        self.model = "fake-model"
        self.prompt_version = "test-1"
        self.input_tokens = 120
        self.output_tokens = 30
        self.cost_usd = 0.0001

    def organize(
        self,
        *,
        text: str,
        title: str,
        existing_tags: list[str],
        context: StageContext,
        collection_title: str | None = None,
        collection_index: int | None = None,
        reuse_existing_tags: bool = False,
    ) -> OrganizationResult:
        self.calls.append(text)
        self.existing_tags_calls.append(list(existing_tags))
        self.collection_calls.append((collection_title, collection_index, reuse_existing_tags))
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake organization failure")
        return OrganizationResult(
            summary=self.summary,
            tags=list(self.tags),
            model=self.model,
            prompt_version=self.prompt_version,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost_usd,
        )


class FakeAudioExtractor:
    def __init__(self) -> None:
        self.real = FfmpegAudioExtractor()
        self.fail_code: str | None = None

    def probe(self, source: Path, *, kind: str) -> None:
        self.real.probe(source, kind=kind)

    def extract(
        self,
        source: Path,
        output_dir: Path,
        *,
        force_transcode: bool,
        context: StageContext,
    ) -> AudioResult:
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake audio extraction failure")
        return self.real.extract(
            source, output_dir, force_transcode=force_transcode, context=context
        )


class FakeBookExtractor:
    def __init__(self) -> None:
        self.real = EpubExtractor()
        self.fail_code: str | None = None

    def validate(self, book_path: Path) -> None:
        self.real.validate(book_path)

    def extract(self, book_path: Path, context: StageContext) -> BookResult:
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake book extraction failure")
        return self.real.extract(book_path, context)


class FakeStack:
    def __init__(self, *, feed_http: FakeHttp | None = None) -> None:
        self.feed_http = feed_http or FakeHttp()
        self.feed_client = make_feed_client(self.feed_http)
        self.downloader = FakeDownloader()
        self.transcriber = FakeTranscriber()
        self.organizer = FakeOrganizer()
        self.audio_extractor = FakeAudioExtractor()
        self.book_extractor = FakeBookExtractor()
        self.video_inspector = FakeVideoInspector()
        self.link_probe = FakeLinkProbe()

    def ports(self) -> Ports:
        return Ports(
            downloader=self.downloader,
            feed_client=self.feed_client,
            audio_extractor=self.audio_extractor,
            transcriber=self.transcriber,
            organizer=self.organizer,
            book_extractor=self.book_extractor,
            video_inspector=self.video_inspector,
            link_probe=self.link_probe,
        )


def wait_until(predicate, *, timeout: float = 10.0, interval: float = 0.02):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        last = value
        time.sleep(interval)
    raise TimeoutError(f"condition not met within {timeout}s (last={last!r})")


__all__ = [
    "FIXTURES",
    "FakeAudioExtractor",
    "FakeBookExtractor",
    "FakeDownloader",
    "FakeHttp",
    "FakeLinkProbe",
    "FakeOrganizer",
    "FakeStack",
    "FakeTranscriber",
    "FakeVideoInspector",
    "FeedPreview",
    "make_feed_client",
    "video_collection",
    "wait_until",
]
