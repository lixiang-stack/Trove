from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from trove.adapters.asr import MlxWhisperTranscriber
from trove.adapters.deepseek import DeepSeekOrganizer
from trove.adapters.downloader import DefaultDownloader
from trove.adapters.epub import EpubExtractor
from trove.adapters.feed import PodcastFeedClient
from trove.adapters.ffmpeg import FfmpegAudioExtractor
from trove.adapters.safe_http import SafeHttpClient
from trove.adapters.search import FtsSearchIndex
from trove.config import Config
from trove.content_package import ContentPackage
from trove.db.engine import create_engine_for, create_session_factory
from trove.ports import (
    AudioExtractor,
    BookExtractor,
    Downloader,
    FeedClient,
    Organizer,
    SearchIndex,
    Transcriber,
)
from trove.services.auth import AuthService
from trove.services.export import ExportService
from trove.services.intake import IntakeService
from trove.services.library import LibraryService
from trove.services.playback import PlaybackService
from trove.services.processing import ProcessingService
from trove.services.reading import ReadingService
from trove.services.search import SearchService
from trove.services.uploads import UploadStore


@dataclass(slots=True)
class Ports:
    downloader: Downloader
    feed_client: FeedClient
    audio_extractor: AudioExtractor
    transcriber: Transcriber
    organizer: Organizer
    book_extractor: BookExtractor


@dataclass(slots=True)
class Runtime:
    config: Config
    engine: Engine
    sessions: sessionmaker[Session]
    package: ContentPackage
    search_index: SearchIndex
    library: LibraryService
    search: SearchService
    reading: ReadingService
    processing: ProcessingService
    intake: IntakeService
    playback: PlaybackService
    export: ExportService
    auth: AuthService
    uploads: UploadStore
    ports: Ports


def default_ports(config: Config) -> Ports:
    http = SafeHttpClient()
    return Ports(
        downloader=DefaultDownloader(config, http),
        feed_client=PodcastFeedClient(http, max_bytes=config.max_feed_bytes),
        audio_extractor=FfmpegAudioExtractor(),
        transcriber=MlxWhisperTranscriber(config.asr_model),
        organizer=DeepSeekOrganizer(config),
        book_extractor=EpubExtractor(),
    )


def build_runtime(config: Config, ports: Ports | None = None) -> Runtime:
    ports = ports or default_ports(config)
    engine = create_engine_for(config)
    sessions = create_session_factory(engine)
    package = ContentPackage(config)
    search_index: SearchIndex = FtsSearchIndex(sessions, package)
    uploads = UploadStore(config)
    library = LibraryService(config, sessions, package, search_index, uploads)
    search = SearchService(sessions, package, search_index, library)
    processing = ProcessingService(
        config,
        sessions,
        package,
        downloader=ports.downloader,
        audio_extractor=ports.audio_extractor,
        transcriber=ports.transcriber,
        organizer=ports.organizer,
        book_extractor=ports.book_extractor,
        search_index=search_index,
        uploads=uploads,
    )
    intake = IntakeService(
        config,
        package,
        library,
        processing,
        ports.feed_client,
        ports.book_extractor,
        uploads,
    )
    playback = PlaybackService(sessions, package, library, search_index)
    reading = ReadingService(sessions, package)
    export = ExportService(config, sessions, package)
    auth = AuthService(config)
    return Runtime(
        config=config,
        engine=engine,
        sessions=sessions,
        package=package,
        search_index=search_index,
        library=library,
        search=search,
        reading=reading,
        processing=processing,
        intake=intake,
        playback=playback,
        export=export,
        auth=auth,
        uploads=uploads,
        ports=ports,
    )
