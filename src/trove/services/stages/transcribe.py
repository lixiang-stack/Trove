from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from trove.clock import utc_ms
from trove.content_package import (
    TRANSCRIPT_FILENAME,
    ArtifactKind,
    ContentPackage,
    SourceDocument,
)
from trove.db.models import Item
from trove.errors import PackageVersionError, ProcessingError, StorageError
from trove.metrics import add, increment
from trove.ports import StageContext, Transcriber
from trove.services.artifacts import ArtifactStore
from trove.services.package_documents import transcript_document

logger = logging.getLogger("trove.processing")


class TranscribeStage:
    def __init__(
        self,
        package: ContentPackage,
        artifacts: ArtifactStore,
        transcriber: Transcriber,
    ) -> None:
        self.package = package
        self.artifacts = artifacts
        self.transcriber = transcriber

    def execute(
        self,
        session: Session,
        item: Item,
        source: SourceDocument,
        context: StageContext,
    ) -> None:
        audio = self.artifacts.get(session, item.id, ArtifactKind.AUDIO)
        if audio is None:
            raise ProcessingError("asr.failed", "Audio is missing; cannot transcribe")
        if not context.force:
            try:
                cached = self.package.read_transcript(item.id)
            except PackageVersionError:
                raise
            except StorageError as exc:
                context.log(f"transcript cache ignored: {exc}")
                cached = None
            if (
                cached is not None
                and cached.input_sha256 == audio.sha256
                and cached.model == self.transcriber.model
            ):
                path = self.package.artifact_path(item.id, TRANSCRIPT_FILENAME)
                self.artifacts.record_document(
                    session, item, kind=ArtifactKind.TRANSCRIPT, path=path
                )
                if cached.language:
                    item.language = cached.language
                item.updated_at = utc_ms()
                saved_seconds = audio.duration_sec or 0
                context.log(
                    "transcript cache hit: "
                    f"audio_sha256={audio.sha256} model={self.transcriber.model}; "
                    f"saved_asr_seconds={saved_seconds} cost=0"
                )
                logger.info(
                    "transcript cache hit",
                    extra={
                        "event": "cache_hit",
                        "cache": "asr",
                        "run_id": context.run_id,
                        "item_id": item.id,
                        "model": self.transcriber.model,
                        "saved_asr_seconds": saved_seconds,
                    },
                )
                increment("external_cache_hits_total", cache="asr")
                add("external_cache_saved_asr_seconds_total", saved_seconds)
                return
            context.log(
                "transcript cache miss: "
                f"audio_sha256={audio.sha256} model={self.transcriber.model}"
            )
            logger.info(
                "transcript cache miss",
                extra={
                    "event": "cache_miss",
                    "cache": "asr",
                    "run_id": context.run_id,
                    "item_id": item.id,
                    "model": self.transcriber.model,
                },
            )
            increment("external_cache_misses_total", cache="asr")
        audio_path = self.package.artifact_path(item.id, audio.path)
        result = self.transcriber.transcribe(audio_path, context)
        path = self.package.write_transcript(
            item.id,
            transcript_document(result, item, input_sha256=audio.sha256),
        )
        self.artifacts.record_document(
            session, item, kind=ArtifactKind.TRANSCRIPT, path=path
        )
        if result.language:
            item.language = result.language
        item.updated_at = utc_ms()
