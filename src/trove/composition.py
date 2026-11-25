from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from trove.adapters.asr import ParaformerTranscriber
from trove.adapters.downloader import DefaultDownloader
from trove.adapters.epub import EpubExtractor
from trove.adapters.feed import PodcastFeedClient
from trove.adapters.ffmpeg import FfmpegAudioExtractor
from trove.adapters.openai_chat import OpenAICompatibleChatClient
from trove.adapters.safe_http import SafeHttpClient
from trove.adapters.search import FtsSearchIndex
from trove.adapters.video_inspect import YtDlpVideoInspector
from trove.config import Config
from trove.content_package import ContentPackage
from trove.db.engine import create_engine_for, create_session_factory
from trove.ports import (
    AudioExtractor,
    BookExtractor,
    Downloader,
    FeedClient,
    LinkProbe,
    Organizer,
    SearchIndex,
    Transcriber,
    VideoInspector,
)
from trove.services.auth import AuthService
from trove.services.collections import CollectionService
from trove.services.devices import DeviceService
from trove.services.export import ExportService
from trove.services.idempotency import IdempotencyService
from trove.services.inspect import InspectService
from trove.services.intake import IntakeService
from trove.services.library import LibraryService
from trove.services.organization import OrganizationWorkflow
from trove.services.playback import PlaybackService
from trove.services.processing import ProcessingService
from trove.services.reading import ReadingService
from trove.services.search import SearchService
from trove.services.sync import SyncService
from trove.services.uploads import UploadStore


@dataclass(slots=True)
class Ports:
    downloader: Downloader
    feed_client: FeedClient
    audio_extractor: AudioExtractor
    transcriber: Transcriber
    organizer: Organizer
    book_extractor: BookExtractor
    video_inspector: VideoInspector
    link_probe: LinkProbe


@dataclass(slots=True)
class Runtime:
    config: Config
    engine: Engine
    sessions: sessionmaker[Session]
    package: ContentPackage
    search_index: SearchIndex
    library: LibraryService
    collections: CollectionService
    search: SearchService
    reading: ReadingService
    processing: ProcessingService
    intake: IntakeService
    inspect: InspectService
    playback: PlaybackService
    export: ExportService
    sync: SyncService
    auth: AuthService
    devices: DeviceService
    uploads: UploadStore
    idempotency: IdempotencyService
    ports: Ports


def default_ports(config: Config) -> Ports:
    http = SafeHttpClient()
    llm_http = httpx.Client(timeout=config.llm.timeout_seconds)
    return Ports(
        downloader=DefaultDownloader(config, http),
        feed_client=PodcastFeedClient(http, max_bytes=config.max_feed_bytes),
        audio_extractor=FfmpegAudioExtractor(),
        transcriber=ParaformerTranscriber(config.asr_model),
        organizer=OrganizationWorkflow(
            config.llm, OpenAICompatibleChatClient(config.llm, llm_http)
        ),
        book_extractor=EpubExtractor(),
        video_inspector=YtDlpVideoInspector(config),
        link_probe=http,
    )


def build_runtime(config: Config, ports: Ports | None = None) -> Runtime:
    ports = ports or default_ports(config)
    engine = create_engine_for(config)
    sessions = create_session_factory(engine)
    package = ContentPackage(config)
    search_index: SearchIndex = FtsSearchIndex(sessions, package)
    uploads = UploadStore(config, ports.book_extractor, ports.audio_extractor)
    library = LibraryService(config, sessions, package, search_index, uploads)
    search = SearchService(sessions, search_index, library)
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
    collections = CollectionService(config, sessions, package, library, processing)
    inspect = InspectService(
        config,
        library,
        collections,
        ports.feed_client,
        ports.video_inspector,
        ports.link_probe,
    )
    intake = IntakeService(
        config,
        package,
        library,
        processing,
        collections,
        ports.feed_client,
        ports.book_extractor,
        ports.audio_extractor,
        uploads,
    )
    playback = PlaybackService(sessions, package, library, search_index)
    reading = ReadingService(sessions, package)
    export = ExportService(config, sessions, package)
    sync = SyncService(config, sessions, package, library)
    auth = AuthService(config)
    devices = DeviceService(config, sessions, auth.rate_limiter)
    idempotency = IdempotencyService(sessions)
    return Runtime(
        config=config,
        engine=engine,
        sessions=sessions,
        package=package,
        search_index=search_index,
        library=library,
        collections=collections,
        search=search,
        reading=reading,
        processing=processing,
        intake=intake,
        inspect=inspect,
        playback=playback,
        export=export,
        sync=sync,
        auth=auth,
        devices=devices,
        uploads=uploads,
        idempotency=idempotency,
        ports=ports,
    )
