from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trove.clock import utc_ms
from trove.content_package import ArtifactKind, ContentPackage, SourceDocument
from trove.db.models import AiResult, Collection, Item, ItemTag, Tag
from trove.domain.organization import MAX_EXISTING_TAGS
from trove.domain.tags import normalize_tag
from trove.errors import TroveError
from trove.ports import Organizer, StageContext
from trove.services.artifacts import ArtifactStore
from trove.services.package_documents import ai_document


class OrganizeStage:
    def __init__(
        self,
        package: ContentPackage,
        artifacts: ArtifactStore,
        organizer: Organizer,
    ) -> None:
        self.package = package
        self.artifacts = artifacts
        self.organizer = organizer

    def execute(
        self,
        session: Session,
        item: Item,
        source: SourceDocument,
        context: StageContext,
    ) -> None:
        source_text = self._item_text(item)
        collection = session.get(Collection, item.collection_id) if item.collection_id else None
        collection_tags = (
            self._collection_tag_vocabulary(session, item.collection_id)
            if item.collection_id
            else []
        )
        result = self.organizer.organize(
            text=source_text,
            title=item.title,
            existing_tags=collection_tags or self._tag_vocabulary(session),
            context=context,
            collection_title=collection.title if collection is not None else None,
            collection_index=item.collection_index,
            reuse_existing_tags=bool(collection_tags),
        )
        generated_at = utc_ms()
        path = self.package.write_ai(item.id, ai_document(result, generated_at))
        self.artifacts.record_document(session, item, kind=ArtifactKind.AI, path=path)
        item.summary = result.summary
        item.updated_at = utc_ms()
        session.add(
            AiResult(
                item_id=item.id,
                run_id=context.run_id,
                summary=result.summary,
                model=result.model,
                prompt_version=result.prompt_version,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                created_at=generated_at,
            )
        )
        self._replace_ai_tags(session, item.id, result.tags)

    def _item_text(self, item: Item) -> str:
        transcript = self.package.read_transcript(item.id)
        if transcript is not None:
            body = "\n".join(segment.text for segment in transcript.segments)
            if body:
                return body
        book = self.package.read_book(item.id)
        if book is not None:
            body = "\n".join(
                paragraph
                for chapter in book.chapters
                for paragraph in chapter.paragraphs
            )
            if body:
                return body
        return ""

    @staticmethod
    def _tag_vocabulary(session: Session) -> list[str]:
        return [
            str(name)
            for name in session.execute(
                select(Tag.name)
                .join(ItemTag, ItemTag.tag_id == Tag.id)
                .group_by(Tag.id)
                .order_by(func.count(ItemTag.item_id).desc(), Tag.normalized_name)
                .limit(MAX_EXISTING_TAGS)
            ).scalars()
        ]

    @staticmethod
    def _collection_tag_vocabulary(session: Session, collection_id: str) -> list[str]:
        return [
            str(name)
            for name in session.execute(
                select(Tag.name)
                .join(ItemTag, ItemTag.tag_id == Tag.id)
                .join(Item, Item.id == ItemTag.item_id)
                .where(
                    Item.collection_id == collection_id,
                    Item.deleted_at.is_(None),
                    ItemTag.source == "ai",
                )
                .group_by(Tag.id)
                .order_by(func.count(ItemTag.item_id).desc(), Tag.normalized_name)
                .limit(MAX_EXISTING_TAGS)
            ).scalars()
        ]

    @staticmethod
    def _replace_ai_tags(session: Session, item_id: str, tags: list[str]) -> None:
        attached = {
            row.tag_id: row
            for row in session.execute(select(ItemTag).where(ItemTag.item_id == item_id)).scalars()
        }
        existing_ai = {tag_id for tag_id, row in attached.items() if row.source == "ai"}
        keep: set[int] = set()
        for raw in tags:
            try:
                display, normalized = normalize_tag(raw)
            except TroveError:
                continue
            tag = session.execute(
                select(Tag).where(Tag.normalized_name == normalized)
            ).scalars().first()
            if tag is None:
                tag = Tag(name=display, normalized_name=normalized)
                session.add(tag)
                session.flush()
            if tag.id not in keep:
                if tag.id not in attached:
                    session.add(ItemTag(item_id=item_id, tag_id=tag.id, source="ai"))
                keep.add(tag.id)
        for tag_id in existing_ai - keep:
            session.delete(attached[tag_id])
