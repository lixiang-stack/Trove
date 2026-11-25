from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from trove.clock import utc_ms
from trove.content_package import ArtifactKind, ContentPackage, SourceDocument
from trove.db.models import Item
from trove.domain.items import SourceType
from trove.errors import ProcessingError
from trove.ports import DOWNLOAD_MEDIA_FILENAME, AudioExtractor, StageContext
from trove.services.artifacts import ArtifactStore
from trove.services.stages.base import sync_source
from trove.services.uploads import UploadStore


class AudioStage:
    def __init__(
        self,
        package: ContentPackage,
        artifacts: ArtifactStore,
        audio_extractor: AudioExtractor,
        uploads: UploadStore,
    ) -> None:
        self.package = package
        self.artifacts = artifacts
        self.audio_extractor = audio_extractor
        self.uploads = uploads

    def execute(
        self,
        session: Session,
        item: Item,
        source: SourceDocument,
        context: StageContext,
    ) -> None:
        if item.source_type in {SourceType.VIDEO_URL, SourceType.PODCAST_EPISODE}:
            media_path = context.work_dir / DOWNLOAD_MEDIA_FILENAME
            if not media_path.is_file():
                raise ProcessingError("download.parse", "Downloaded media file not found")
            force_transcode = True
        else:
            if not item.source_path:
                raise ProcessingError(
                    "storage.source_missing", "Local source file path is missing"
                )
            media_path = Path(item.source_path)
            if not media_path.is_file():
                raise ProcessingError(
                    "storage.source_missing", "Source file does not exist or is not readable"
                )
            force_transcode = item.source_type == SourceType.LOCAL_VIDEO
        result = self.audio_extractor.extract(
            media_path,
            context.work_dir,
            force_transcode=force_transcode,
            context=context,
        )
        artifact = self.artifacts.install(
            session,
            item,
            kind=ArtifactKind.AUDIO,
            temp_path=result.path,
            extension=result.extension,
            mime=result.mime,
            duration=result.duration_sec,
        )
        item.duration_sec = result.duration_sec or item.duration_sec
        item.updated_at = utc_ms()
        if (
            source.uploaded
            and item.source_path
            and self.uploads.discard_for_path(item.source_path)
        ):
            item.source_path = None
        sync_source(self.package, item, source)
        if item.source_type in {SourceType.VIDEO_URL, SourceType.PODCAST_EPISODE}:
            media_path.unlink(missing_ok=True)
        context.log(f"audio artifact {artifact.path} ({artifact.size} bytes)")
