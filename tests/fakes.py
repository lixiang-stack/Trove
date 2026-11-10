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
from trove.errors import ProcessingCancelled, ProcessingError
from trove.ports import (
    AudioResult,
    BookResult,
    DownloadResult,
    FeedClient,
    FeedPreview,
    OrganizationResult,
    StageContext,
    TranscriptResult,
    TranscriptSegmentData,
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


class FakeDownloader:
    def __init__(self, fixture: Path | None = None) -> None:
        self.fixture = fixture or FIXTURES / "short.wav"
        self.calls: list[dict] = []
        self.fail_code: str | None = None
        self.started = threading.Event()
        self.block = threading.Event()
        self.blocked = False

    def download(self, source: dict, context: StageContext) -> DownloadResult:
        self.calls.append(source)
        self.started.set()
        if self.blocked:
            self.block.clear()
            while not self.block.wait(0.02):
                if context.should_cancel():
                    raise ProcessingCancelled("cancelled")
        if self.fail_code:
            raise ProcessingError(self.fail_code, "fake download failure")
        destination = context.work_dir / "download.wav"
        shutil.copyfile(self.fixture, destination)
        title = (
            source.get("title")
            if source.get("source_type") == "podcast_episode"
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
    ) -> OrganizationResult:
        self.calls.append(text)
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

    def ports(self) -> Ports:
        return Ports(
            downloader=self.downloader,
            feed_client=self.feed_client,
            audio_extractor=self.audio_extractor,
            transcriber=self.transcriber,
            organizer=self.organizer,
            book_extractor=self.book_extractor,
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
    "FakeOrganizer",
    "FakeStack",
    "FakeTranscriber",
    "FeedPreview",
    "make_feed_client",
    "wait_until",
]
