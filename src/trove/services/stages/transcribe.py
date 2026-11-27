from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from trove import metrics, telemetry
from trove.clock import utc_ms
from trove.content_package import (
    TRANSCRIPT_FILENAME,
    ArtifactKind,
    ContentPackage,
    SourceDocument,
)
from trove.db.models import Item
from trove.errors import PackageVersionError, ProcessingError, StorageError
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
                metrics.record_external_cache_hit("asr")
                metrics.EXTERNAL_CACHE_SAVED_ASR_SECONDS.inc(saved_seconds)
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
            metrics.record_external_cache_miss("asr")
        audio_path = self.package.artifact_path(item.id, audio.path)
        started = time.monotonic()
        with telemetry.span(
            "trove.asr.transcribe",
            attributes={
                "trove.run_id": context.run_id,
                "trove.item_id": item.id,
                "trove.stage": "transcribing",
            },
        ):
            result = self.transcriber.transcribe(audio_path, context)
        if audio.duration_sec and audio.duration_sec > 0:
            metrics.record_asr_realtime_factor(
                (time.monotonic() - started) / audio.duration_sec
            )
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
