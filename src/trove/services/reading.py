from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from trove.db.models import BookChapter, BookParagraph, Item
from trove.errors import NotFoundError


@dataclass(slots=True)
class BookChapterView:
    chapter: BookChapter
    paragraphs: list[BookParagraph] = field(default_factory=list)


class ReadingService:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions

    def chapters(self, item_id: str) -> list[BookChapterView]:
        with self.sessions() as session:
            if session.get(Item, item_id) is None:
                raise NotFoundError("Content not found")
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
