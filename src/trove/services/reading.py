from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.db.models import BookChapter, BookParagraph, Item
from trove.domain.items import ConsumptionState
from trove.domain.reading import BookLocator, parse_book_locator, serialize_book_locator
from trove.errors import NotFoundError, ValidationError


@dataclass(slots=True)
class BookChapterView:
    chapter: BookChapter
    paragraphs: list[BookParagraph] = field(default_factory=list)


class ReadingService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def chapters(self, item_id: str) -> list[BookChapterView]:
        with self.sessions() as session:
            self._require_item(session, item_id)
            chapters = list(
                session.execute(
                    select(BookChapter)
                    .where(BookChapter.item_id == item_id)
                    .order_by(BookChapter.chapter_index)
                ).scalars()
            )
            paragraphs = list(
                session.execute(
                    select(BookParagraph)
                    .where(BookParagraph.item_id == item_id)
                    .order_by(BookParagraph.chapter_index, BookParagraph.paragraph_index)
                ).scalars()
            )
        grouped: dict[int, list[BookParagraph]] = {}
        for paragraph in paragraphs:
            grouped.setdefault(paragraph.chapter_index, []).append(paragraph)
        return [
            BookChapterView(chapter=chapter, paragraphs=grouped.get(chapter.chapter_index, []))
            for chapter in chapters
        ]

    def chapter(self, item_id: str, chapter_index: int) -> BookChapterView:
        with self.sessions() as session:
            self._require_item(session, item_id)
            chapter = session.execute(
                select(BookChapter).where(
                    BookChapter.item_id == item_id,
                    BookChapter.chapter_index == chapter_index,
                )
            ).scalars().first()
            if chapter is None:
                raise NotFoundError(
                    "Chapter not found", details={"code": "book.chapter_not_found"}
                )
            paragraphs = list(
                session.execute(
                    select(BookParagraph)
                    .where(
                        BookParagraph.item_id == item_id,
                        BookParagraph.chapter_index == chapter_index,
                    )
                    .order_by(BookParagraph.paragraph_index)
                ).scalars()
            )
        return BookChapterView(chapter=chapter, paragraphs=paragraphs)

    def locator(self, item_id: str) -> BookLocator | None:
        with self.sessions() as session:
            item = self._require_item(session, item_id)
            return parse_book_locator(item.book_locator)

    def save_progress(
        self,
        item_id: str,
        locator: BookLocator,
        *,
        consumption_state: str | None = None,
    ) -> None:
        if consumption_state is not None and consumption_state not in {
            ConsumptionState.UNSTARTED,
            ConsumptionState.IN_PROGRESS,
            ConsumptionState.FINISHED,
        }:
            raise ValidationError(
                "Invalid consumption state", details={"code": "progress.invalid_state"}
            )
        with self.sessions() as session:
            item = self._require_item(session, item_id)
            chapter = session.execute(
                select(BookChapter.id).where(
                    BookChapter.item_id == item_id,
                    BookChapter.chapter_index == locator.chapter_index,
                )
            ).first()
            if chapter is None:
                raise ValidationError(
                    "Chapter not found", details={"code": "book.chapter_not_found"}
                )
            item.book_locator = serialize_book_locator(locator)
            if consumption_state is not None:
                item.consumption_state = consumption_state
            elif item.consumption_state != ConsumptionState.FINISHED and (
                locator.chapter_index > 0
                or (locator.paragraph_index or 0) > 0
                or locator.scroll_ratio > 0.001
            ):
                item.consumption_state = ConsumptionState.IN_PROGRESS
            now = utc_ms()
            item.last_consumed_at = now
            item.updated_at = now
            session.commit()

    @staticmethod
    def _require_item(session: Session, item_id: str) -> Item:
        item = session.get(Item, item_id)
        if item is None:
            raise NotFoundError("Content not found")
        return item
