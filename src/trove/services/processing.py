from __future__ import annotations

import uuid
from collections.abc import Callable, Collection

from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
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
        worker_id: str | None = None,
        clock: Callable[[], int] = utc_ms,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package
        self._worker_id = worker_id
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
            config, sessions, package, search_index, stages, clock=clock
        )

    def create_run(self, item_id: str) -> Run:
        return self._coordinator.create_run(item_id)

    def claim_next(
        self,
        worker_id: str | None = None,
        *,
        stages: Collection[str] | None = None,
    ) -> str | None:
        return self._coordinator.claim_next(
            self._worker(worker_id), stages=stages
        )

    def process(self, run_id: str, worker_id: str | None = None) -> None:
        self._coordinator.process(run_id, self._worker(worker_id))

    def retry(self, item_id: str) -> Run:
        return self._coordinator.retry(item_id)

    def reprocess(self, item_id: str, from_stage: str) -> Run:
        return self._coordinator.reprocess(item_id, from_stage)

    def cancel(self, run_id: str) -> Run:
        return self._coordinator.cancel(run_id)

    def cancel_item(self, item_id: str) -> Run:
        return self._coordinator.cancel_item(item_id)

    def reap_expired(self, now: int | None = None) -> int:
        return self._coordinator.reap_expired(now)

    def recover_active_runs(self) -> int:
        return self._coordinator.recover_active_runs()

    def heartbeat(self, run_id: str, worker_id: str) -> None:
        self._coordinator.heartbeat(run_id, worker_id)

    def mark_worker_failure(self, run_id: str, worker_id: str) -> None:
        self._coordinator.mark_worker_failure(run_id, worker_id)

    def _worker(self, worker_id: str | None) -> str:
        if worker_id is not None:
            return worker_id
        if self._worker_id is None:
            self._worker_id = f"worker-{uuid.uuid4().hex[:12]}"
        return self._worker_id
