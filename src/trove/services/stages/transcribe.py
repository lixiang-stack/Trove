from __future__ import annotations

from sqlalchemy.orm import Session

from trove.clock import utc_ms
from trove.content_package import ArtifactKind, ContentPackage, SourceDocument
from trove.db.models import Item
from trove.errors import ProcessingError
from trove.ports import StageContext, Transcriber
from trove.services.artifacts import ArtifactStore
from trove.services.package_documents import transcript_document


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
        audio_path = self.package.artifact_path(item.id, audio.path)
        result = self.transcriber.transcribe(audio_path, context)
        path = self.package.write_transcript(item.id, transcript_document(result, item))
        self.artifacts.record_document(
            session, item, kind=ArtifactKind.TRANSCRIPT, path=path
        )
        if result.language:
            item.language = result.language
        item.updated_at = utc_ms()
