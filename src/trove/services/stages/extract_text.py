from __future__ import annotations

from sqlalchemy.orm import Session

from trove.clock import utc_ms
from trove.content_package import ArtifactKind, ContentPackage, SourceDocument
from trove.db.models import Item
from trove.domain.books import meaningful_title
from trove.errors import ProcessingError
from trove.ports import BookExtractor, BookResult, StageContext
from trove.services.artifacts import ArtifactStore
from trove.services.package_documents import book_document
from trove.services.stages.base import sync_source


class ExtractTextStage:
    def __init__(
        self,
        package: ContentPackage,
        artifacts: ArtifactStore,
        book_extractor: BookExtractor,
    ) -> None:
        self.package = package
        self.artifacts = artifacts
        self.book_extractor = book_extractor

    def execute(
        self,
        session: Session,
        item: Item,
        source: SourceDocument,
        context: StageContext,
    ) -> None:
        book = self.artifacts.get(session, item.id, ArtifactKind.BOOK)
        if book is None:
            raise ProcessingError("epub.invalid", "EPUB file is missing")
        book_path = self.package.artifact_path(item.id, book.path)
        result = self.book_extractor.extract(book_path, context)
        title = self._book_title(result, item)
        path = self.package.write_book(item.id, book_document(result, title=title))
        self.artifacts.record_document(
            session, item, kind=ArtifactKind.BOOK_JSON, path=path
        )
        if result.cover is not None:
            cover_temp = context.work_dir / f"cover{result.cover.extension}"
            cover_temp.write_bytes(result.cover.data)
            self.artifacts.install(
                session,
                item,
                kind=ArtifactKind.COVER,
                temp_path=cover_temp,
                extension=result.cover.extension,
                mime=result.cover.mime,
                duration=None,
            )
        else:
            self.artifacts.remove(session, item.id, ArtifactKind.COVER)
        item.title = title
        item.author = result.author or item.author
        item.language = result.language or item.language
        item.updated_at = utc_ms()
        sync_source(self.package, item, source)

    @staticmethod
    def _book_title(result: BookResult, item: Item) -> str:
        for candidate in (result.title, item.title):
            title = meaningful_title(candidate)
            if title:
                return title
        for chapter in result.chapters:
            title = meaningful_title(chapter.title)
            if title:
                return title
        return "Untitled book"
