from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session, sessionmaker

from trove.content_package import BookChapterDocument, ContentPackage
from trove.db.models import Item
from trove.domain.reading import BookLocator, parse_book_locator
from trove.errors import NotFoundError


@dataclass(slots=True)
class BookParagraphView:
    paragraph_index: int
    text: str


@dataclass(slots=True)
class BookChapterView:
    chapter: BookChapterDocument
    paragraphs: list[BookParagraphView] = field(default_factory=list)


class ReadingService:
    def __init__(self, sessions: sessionmaker[Session], package: ContentPackage) -> None:
        self.sessions = sessions
        self.package = package

    def chapters(self, item_id: str) -> list[BookChapterView]:
        with self.sessions() as session:
            self._require_item(session, item_id)
        document = self.package.read_book(item_id)
        if document is None:
            return []
        return [self._chapter_view(chapter) for chapter in document.chapters]

    def chapter(self, item_id: str, chapter_index: int) -> BookChapterView:
        with self.sessions() as session:
            self._require_item(session, item_id)
        document = self.package.read_book(item_id)
        if document is not None:
            for chapter in document.chapters:
                if chapter.chapter_index == chapter_index:
                    return self._chapter_view(chapter)
        raise NotFoundError(
            "Chapter not found", details={"code": "book.chapter_not_found"}
        )

    @staticmethod
    def _chapter_view(chapter: BookChapterDocument) -> BookChapterView:
        return BookChapterView(
            chapter=chapter,
            paragraphs=[
                BookParagraphView(paragraph_index=index, text=text)
                for index, text in enumerate(chapter.paragraphs)
            ],
        )

    def locator(self, item_id: str) -> BookLocator | None:
        with self.sessions() as session:
            item = self._require_item(session, item_id)
            return parse_book_locator(item.book_locator)

    @staticmethod
    def _require_item(session: Session, item_id: str) -> Item:
        item = session.get(Item, item_id)
        if item is None or item.deleted_at is not None:
            raise NotFoundError("Content not found")
        return item
