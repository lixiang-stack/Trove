from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from trove import metrics, telemetry
from trove.clock import utc_ms
from trove.content_package import (
    AI_FILENAME,
    AiDocument,
    ArtifactKind,
    ContentPackage,
    SourceDocument,
)
from trove.db.models import AiResult, Collection, Item, ItemTag, Tag
from trove.domain.cache import ai_input_sha256
from trove.domain.organization import MAX_EXISTING_TAGS
from trove.domain.search import is_cjk
from trove.domain.tags import normalize_tag
from trove.errors import PackageVersionError, StorageError, TroveError
from trove.ports import Organizer, StageContext
from trove.services.artifacts import ArtifactStore
from trove.services.package_documents import ai_document

logger = logging.getLogger("trove.processing")


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
        input_sha256 = ai_input_sha256(source_text)
        identity = self.organizer.cache_identity
        if identity is not None and not context.force:
            model = identity.model
            prompt_version = identity.prompt_version
            cached = self._cached_ai(
                item,
                input_sha256=input_sha256,
                model=model,
                prompt_version=prompt_version,
            )
            if cached is not None:
                self._apply_cached(session, item, cached, context)
                return
            context.log(
                "ai cache miss: "
                f"input_sha256={input_sha256} model={model} "
                f"prompt_version={prompt_version}"
            )
            logger.info(
                "ai cache miss",
                extra={
                    "event": "cache_miss",
                    "cache": "ai",
                    "run_id": context.run_id,
                    "item_id": item.id,
                    "model": model,
                    "prompt_version": prompt_version,
                },
            )
            metrics.record_external_cache_miss("ai")
        elif context.force:
            context.log("ai cache bypassed: explicit reprocess")
            logger.info(
                "ai cache bypassed",
                extra={
                    "event": "cache_bypass",
                    "cache": "ai",
                    "run_id": context.run_id,
                    "item_id": item.id,
                },
            )
        collection = session.get(Collection, item.collection_id) if item.collection_id else None
        collection_tags = (
            self._collection_tag_vocabulary(session, item.collection_id)
            if item.collection_id
            else []
        )
        with telemetry.span(
            "trove.llm.organize",
            attributes={
                "trove.run_id": context.run_id,
                "trove.item_id": item.id,
                "trove.stage": "organizing",
            },
        ):
            result = self.organizer.organize(
                text=source_text,
                title=item.title,
                existing_tags=collection_tags or self._tag_vocabulary(session),
                context=context,
                collection_title=collection.title if collection is not None else None,
                collection_index=item.collection_index,
                reuse_existing_tags=bool(collection_tags),
            )
        metrics.record_llm_usage(
            result.input_tokens, result.output_tokens, result.cost_usd or 0.0
        )
        generated_at = utc_ms()
        path = self.package.write_ai(
            item.id,
            ai_document(result, generated_at, input_sha256=input_sha256),
        )
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
                input_sha256=input_sha256,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                created_at=generated_at,
            )
        )
        self._replace_ai_tags(session, item.id, result.tags)

    def _cached_ai(
        self,
        item: Item,
        *,
        input_sha256: str,
        model: str,
        prompt_version: str,
    ) -> AiDocument | None:
        try:
            document = self.package.read_ai(item.id)
        except PackageVersionError:
            raise
        except StorageError:
            return None
        if (
            document is None
            or document.input_sha256 != input_sha256
            or document.model != model
            or document.prompt_version != prompt_version
        ):
            return None
        return document

    def _apply_cached(
        self,
        session: Session,
        item: Item,
        document: AiDocument,
        context: StageContext,
    ) -> None:
        path = self.package.artifact_path(item.id, AI_FILENAME)
        self.artifacts.record_document(session, item, kind=ArtifactKind.AI, path=path)
        item.summary = document.summary
        item.updated_at = utc_ms()
        self._replace_ai_tags(session, item.id, document.tags)
        context.log(
            "ai cache hit: "
            f"input_sha256={document.input_sha256} model={document.model} "
            f"prompt_version={document.prompt_version}; cached=true cost=0 "
            f"saved_input_tokens={document.input_tokens} "
            f"saved_output_tokens={document.output_tokens} "
            f"saved_cost_usd={document.cost_usd or 0}"
        )
        logger.info(
            "ai cache hit",
            extra={
                "event": "cache_hit",
                "cache": "ai",
                "run_id": context.run_id,
                "item_id": item.id,
                "model": document.model,
                "prompt_version": document.prompt_version,
                "saved_input_tokens": document.input_tokens,
                "saved_output_tokens": document.output_tokens,
                "saved_cost_usd": document.cost_usd or 0,
            },
        )
        metrics.record_external_cache_hit("ai")
        metrics.record_external_cache_saved_tokens(
            input_tokens=document.input_tokens,
            output_tokens=document.output_tokens,
            cost_usd=document.cost_usd or 0,
        )

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
        names = [
            str(name)
            for name in session.execute(
                select(Tag.name)
                .join(ItemTag, ItemTag.tag_id == Tag.id)
                .group_by(Tag.id)
                .order_by(func.count(ItemTag.item_id).desc(), Tag.normalized_name)
            ).scalars()
        ]
        return [
            name for name in names if any(is_cjk(char) for char in name)
        ][:MAX_EXISTING_TAGS]

    @staticmethod
    def _collection_tag_vocabulary(session: Session, collection_id: str) -> list[str]:
        names = [
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
            ).scalars()
        ]
        return [
            name for name in names if any(is_cjk(char) for char in name)
        ][:MAX_EXISTING_TAGS]

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
