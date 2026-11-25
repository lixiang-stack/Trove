from __future__ import annotations

from sqlalchemy.orm import Session

from trove.clock import utc_ms
from trove.content_package import ArtifactKind, ContentPackage, SourceDocument
from trove.db.models import Item
from trove.domain.items import SourceType
from trove.ports import BookExtractor, Downloader, StageContext
from trove.services.artifacts import ArtifactStore
from trove.services.stages.base import sync_source


class DownloadStage:
    def __init__(
        self,
        package: ContentPackage,
        artifacts: ArtifactStore,
        downloader: Downloader,
        book_extractor: BookExtractor,
    ) -> None:
        self.package = package
        self.artifacts = artifacts
        self.downloader = downloader
        self.book_extractor = book_extractor

    def execute(
        self,
        session: Session,
        item: Item,
        source: SourceDocument,
        context: StageContext,
    ) -> None:
        result = self.downloader.download(source, context)
        item.title = result.title or item.title
        item.author = result.author or item.author
        item.published_at = result.published_at or item.published_at
        item.duration_sec = result.duration_sec or item.duration_sec
        item.language = result.language or item.language
        item.updated_at = utc_ms()
        sync_source(self.package, item, source)
        if source.source_type == SourceType.EPUB_URL:
            self.book_extractor.validate(result.path)
            self.artifacts.install(
                session,
                item,
                kind=ArtifactKind.BOOK,
                temp_path=result.path,
                extension=None,
                mime="application/epub+zip",
                duration=None,
            )
            context.log(f"downloaded EPUB {result.path.name}")
            return
        context.log(f"downloaded media {result.path.name}")
