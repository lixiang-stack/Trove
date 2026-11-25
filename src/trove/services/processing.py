from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from trove.content_package import ContentPackage
from trove.db.models import Run
from trove.domain.items import (
    STAGE_DOWNLOADING,
    STAGE_EXTRACTING_AUDIO,
    STAGE_EXTRACTING_TEXT,
    STAGE_INDEXING,
    STAGE_ORGANIZING,
    STAGE_TRANSCRIBING,
)
from trove.ports import (
    AudioExtractor,
    BookExtractor,
    Downloader,
    Organizer,
    SearchIndex,
    Transcriber,
)
from trove.services.artifacts import ArtifactStore
from trove.services.run_coordinator import RunCoordinator
from trove.services.stages.audio import AudioStage
from trove.services.stages.base import StageHandler
from trove.services.stages.download import DownloadStage
from trove.services.stages.extract_text import ExtractTextStage
from trove.services.stages.index import IndexStage
from trove.services.stages.organize import OrganizeStage
from trove.services.stages.transcribe import TranscribeStage
from trove.services.uploads import UploadStore


class ProcessingService:
    """Compatibility facade for the processing entry points.

    Run lifecycle and stage execution live in ``RunCoordinator`` and
    ``services/stages``; this class keeps the public surface used by the
    composition root, services, and HTTP handlers stable.
    """

    def __init__(
        self,
        config,
        sessions: sessionmaker[Session],
        package: ContentPackage,
        *,
        downloader: Downloader,
        audio_extractor: AudioExtractor,
        transcriber: Transcriber,
        organizer: Organizer,
        book_extractor: BookExtractor,
        search_index: SearchIndex,
        uploads: UploadStore,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package
        artifacts = ArtifactStore(package)
        stages: dict[str, StageHandler] = {
            STAGE_DOWNLOADING: DownloadStage(
                package, artifacts, downloader, book_extractor
            ),
            STAGE_EXTRACTING_AUDIO: AudioStage(
                package, artifacts, audio_extractor, uploads
            ),
            STAGE_TRANSCRIBING: TranscribeStage(package, artifacts, transcriber),
            STAGE_EXTRACTING_TEXT: ExtractTextStage(
                package, artifacts, book_extractor
            ),
            STAGE_ORGANIZING: OrganizeStage(package, artifacts, organizer),
            STAGE_INDEXING: IndexStage(search_index),
        }
        self._coordinator = RunCoordinator(
            config, sessions, package, search_index, stages
        )

    def create_run(self, item_id: str) -> Run:
        return self._coordinator.create_run(item_id)

    def claim_next(self) -> str | None:
        return self._coordinator.claim_next()

    def process(self, run_id: str) -> None:
        self._coordinator.process(run_id)

    def retry(self, item_id: str) -> Run:
        return self._coordinator.retry(item_id)

    def reprocess(self, item_id: str, from_stage: str) -> Run:
        return self._coordinator.reprocess(item_id, from_stage)

    def cancel(self, run_id: str) -> Run:
        return self._coordinator.cancel(run_id)

    def cancel_item(self, item_id: str) -> Run:
        return self._coordinator.cancel_item(item_id)

    def reclaim_stale_runs(self) -> int:
        return self._coordinator.reclaim_stale_runs()

    def heartbeat(self, run_id: str) -> None:
        self._coordinator.heartbeat(run_id)

    def mark_worker_failure(self, run_id: str) -> None:
        self._coordinator.mark_worker_failure(run_id)
