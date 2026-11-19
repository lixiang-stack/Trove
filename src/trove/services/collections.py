from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.content_package import ContentPackage
from trove.db.models import Collection, Item
from trove.db.sequences import next_sequence
from trove.domain.items import (
    PLATFORM_LABELS,
    ConsumptionState,
    RunState,
)
from trove.errors import NotFoundError, ValidationError
from trove.services.library import ItemBundle, LibraryService, item_bundle
from trove.services.package_documents import source_document


@dataclass(slots=True)
class CollectionBundle:
    collection: Collection
    items: list[ItemBundle] = field(default_factory=list)

    @property
    def episode_count(self) -> int:
        return len(self.items)

    @property
    def total_duration_sec(self) -> float:
        return sum(item.item.duration_sec or 0.0 for item in self.items)

    @property
    def status_counts(self) -> dict[str, int]:
        counts = {
            "queued": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "total": len(self.items),
        }
        for bundle in self.items:
            state = bundle.run_state
            if state == RunState.QUEUED:
                counts["queued"] += 1
            elif state == RunState.FAILED:
                counts["failed"] += 1
            elif state == RunState.CANCELLED:
                counts["cancelled"] += 1
            elif state in {RunState.COMPLETED}:
                counts["completed"] += 1
            else:
                counts["processing"] += 1
        return counts

    @property
    def consumption_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {
            str(ConsumptionState.UNSTARTED): 0,
            str(ConsumptionState.IN_PROGRESS): 0,
            str(ConsumptionState.FINISHED): 0,
        }
        for bundle in self.items:
            key = str(bundle.consumption_state)
            counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def failed_items(self) -> list[ItemBundle]:
        return [bundle for bundle in self.items if bundle.status_category == "failed"]


@dataclass(slots=True)
class CollectionCreateResult:
    collection: CollectionBundle
    added_count: int
    attached_count: int
    skipped_count: int
    run_count: int
    warnings: list[dict[str, Any]] = field(default_factory=list)


def collection_block(collection: Collection, index: int | None) -> dict[str, Any]:
    return {
        "source_key": collection.source_key,
        "title": collection.title,
        "author": collection.author,
        "platform": collection.platform,
        "source_url": collection.source_url_canonical or collection.source_url_raw,
        "index": index,
    }


class CollectionService:
    def __init__(
        self,
        config,
        sessions: sessionmaker[Session],
        package: ContentPackage,
        library: LibraryService,
        processing,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package
        self.library = library
        self.processing = processing

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get(self, collection_id: str) -> CollectionBundle:
        with self.sessions() as session:
            collection = session.get(Collection, collection_id)
            if collection is None or collection.deleted_at is not None:
                raise NotFoundError("Collection not found")
            items = [
                item_bundle(session, item)
                for item in session.execute(
                    select(Item)
                    .where(
                        Item.collection_id == collection.id,
                        Item.deleted_at.is_(None),
                    )
                    .order_by(Item.collection_index, Item.created_at, Item.id)
                ).scalars()
            ]
            return CollectionBundle(collection=collection, items=items)

    def find_by_source_key(self, source_key: str) -> CollectionBundle | None:
        with self.sessions() as session:
            collection = session.execute(
                select(Collection).where(
                    Collection.source_key == source_key,
                    Collection.deleted_at.is_(None),
                )
            ).scalars().first()
            if collection is None:
                return None
            items = [
                item_bundle(session, item)
                for item in session.execute(
                    select(Item)
                    .where(
                        Item.collection_id == collection.id,
                        Item.deleted_at.is_(None),
                    )
                    .order_by(Item.collection_index, Item.created_at, Item.id)
                ).scalars()
            ]
            return CollectionBundle(collection=collection, items=items)

    def list_collections(self) -> list[CollectionBundle]:
        with self.sessions() as session:
            collections = list(
                session.execute(
                    select(Collection)
                    .where(Collection.deleted_at.is_(None))
                    .order_by(Collection.created_at.desc(), Collection.id.desc())
                ).scalars()
            )
            result = []
            for collection in collections:
                items = [
                    item_bundle(session, item)
                    for item in session.execute(
                        select(Item)
                        .where(
                            Item.collection_id == collection.id,
                            Item.deleted_at.is_(None),
                        )
                        .order_by(Item.collection_index, Item.created_at, Item.id)
                    ).scalars()
                ]
                result.append(CollectionBundle(collection=collection, items=items))
            return result

    def count(self) -> int:
        with self.sessions() as session:
            return len(
                session.execute(
                    select(Collection.id).where(Collection.deleted_at.is_(None))
                ).scalars().all()
            )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def create_or_update(
        self,
        *,
        source_key: str,
        source_url_raw: str | None,
        source_url_canonical: str | None,
        platform: str,
        title: str,
        author: str | None,
        episode_count: int = 0,
        total_duration_sec: float | None = None,
    ) -> tuple[Collection, bool]:
        now = utc_ms()
        with self.sessions() as session:
            existing = session.execute(
                select(Collection).where(Collection.source_key == source_key)
            ).scalars().first()
            if existing is not None:
                metadata_changed = (
                    existing.deleted_at is not None
                    or (title and title != existing.title)
                    or (author and author != existing.author)
                    or (source_url_raw and source_url_raw != existing.source_url_raw)
                )
                existing.deleted_at = None
                if title:
                    existing.title = title
                if author:
                    existing.author = author
                existing.platform = platform
                existing.source_url_raw = source_url_raw or existing.source_url_raw
                existing.source_url_canonical = (
                    source_url_canonical or existing.source_url_canonical
                )
                existing.episode_count = episode_count
                existing.total_duration_sec = total_duration_sec
                existing.updated_at = now
                if metadata_changed:
                    self._touch_items(session, existing.id, now)
                session.commit()
                return existing, True
            collection = Collection(
                id=str(uuid.uuid4()),
                source_key=source_key,
                source_url_raw=source_url_raw,
                source_url_canonical=source_url_canonical,
                platform=platform,
                title=title or "Untitled collection",
                author=author,
                episode_count=episode_count,
                total_duration_sec=total_duration_sec,
                created_at=now,
                updated_at=now,
            )
            session.add(collection)
            session.commit()
            return collection, False

    def attach_item(
        self, collection: Collection, item: ItemBundle, index: int | None
    ) -> None:
        if item.item.collection_id not in {None, collection.id}:
            raise ValidationError(
                "Episode already belongs to another collection",
                details={"code": "collection.episode_conflict"},
            )
        now = utc_ms()
        with self.sessions() as session:
            db_item = session.get(Item, item.item.id)
            if db_item is None:
                raise NotFoundError("Content not found")
            db_item.collection_id = collection.id
            db_item.collection_index = index
            db_item.updated_at = now
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValidationError(
                    "Collection episode order conflicts",
                    details={"code": "collection.episode_invalid"},
                ) from exc
        self._write_collection_source(item.item.id, collection, index)

    def detach_item(self, item_id: str) -> None:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                return
            item.collection_id = None
            item.collection_index = None
            item.updated_at = utc_ms()
            session.commit()
        self._write_collection_source(item_id, None, None)

    def refresh_counts(self, collection_id: str) -> CollectionBundle:
        bundle = self.get(collection_id)
        now = utc_ms()
        with self.sessions() as session:
            collection = session.get(Collection, collection_id)
            if collection is None:
                raise NotFoundError("Collection not found")
            collection.episode_count = bundle.episode_count
            collection.total_duration_sec = bundle.total_duration_sec or None
            collection.updated_at = now
            session.commit()
        return self.get(collection_id)

    def delete(self, collection_id: str, *, delete_items: bool) -> int:
        bundle = self.get(collection_id)
        now = utc_ms()
        item_ids = [item.item.id for item in bundle.items]
        with self.sessions() as session:
            collection = session.get(Collection, collection_id)
            if collection is None:
                raise NotFoundError("Collection not found")
            collection.deleted_at = now
            collection.updated_at = now
            if not delete_items:
                for item_id in item_ids:
                    item = session.get(Item, item_id)
                    if item is not None:
                        item.collection_id = None
                        item.collection_index = None
                        item.updated_at = now
            session.commit()
        if delete_items:
            for item_id in item_ids:
                try:
                    self.library.delete(item_id, reset_consumption=True)
                except NotFoundError:
                    continue
        else:
            for item_id in item_ids:
                self._write_collection_source(item_id, None, None)
        return len(item_ids)

    def retry_failed(self, collection_id: str) -> int:
        bundle = self.get(collection_id)
        retried = 0
        for entry in bundle.items:
            if entry.run is not None and entry.run.state in {
                RunState.FAILED,
                RunState.CANCELLED,
            }:
                self.processing.retry(entry.item.id)
                retried += 1
        return retried

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def payload(self, bundle: CollectionBundle, *, include_items: bool = False) -> dict[str, Any]:
        collection = bundle.collection
        items = bundle.items
        cover_item = next((entry for entry in items if entry.cover_artifact), None)
        payload: dict[str, Any] = {
            "id": collection.id,
            "source_key": collection.source_key,
            "platform": collection.platform,
            "platform_label": PLATFORM_LABELS.get(
                collection.platform, collection.platform
            ),
            "source_url_raw": collection.source_url_raw,
            "source_url_canonical": collection.source_url_canonical,
            "title": collection.title,
            "author": collection.author,
            "episode_count": bundle.episode_count,
            "total_duration_sec": bundle.total_duration_sec or None,
            "created_at": collection.created_at,
            "updated_at": collection.updated_at,
            "status": bundle.status_counts,
            "consumption": bundle.consumption_counts,
            "cover_url": (
                f"/api/items/{cover_item.item.id}/cover" if cover_item else None
            ),
        }
        if include_items:
            payload["items"] = [self._item_summary(entry) for entry in items]
        return payload

    def _item_summary(self, bundle: ItemBundle) -> dict[str, Any]:
        run = bundle.run
        return {
            "id": bundle.item.id,
            "title": bundle.item.title,
            "collection_index": bundle.item.collection_index,
            "duration_sec": bundle.item.duration_sec,
            "processing_state": bundle.run_state,
            "processing_label": bundle.processing_label,
            "status_category": bundle.status_category,
            "consumption_state": bundle.consumption_state,
            "consumption_label": bundle.consumption_label,
            "has_audio": bundle.audio_artifact is not None,
            "has_book": bundle.book_artifact is not None,
            "cover_url": (
                f"/api/items/{bundle.item.id}/cover"
                if bundle.cover_artifact is not None
                else None
            ),
            "error_code": run.error_code if run is not None else None,
            "error_message": (
                self.library.public_text(
                    run.error_message, source_path=bundle.item.source_path
                )
                if run is not None
                else None
            ),
        }

    # ------------------------------------------------------------------
    # Content package
    # ------------------------------------------------------------------
    def _write_collection_source(
        self, item_id: str, collection: Collection | None, index: int | None
    ) -> None:
        base = self.package.read_source(item_id)
        item = None
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                return
        if base is None:
            base = source_document(item)
        document = source_document(item, base=base)
        if collection is not None:
            document.extra["collection"] = collection_block(collection, index)
        else:
            document.extra.pop("collection", None)
        self.package.write_source(item_id, document)

    @staticmethod
    def _touch_items(session: Session, collection_id: str, now: int) -> None:
        # Collection metadata is mirrored onto every episode so Android can
        # derive the card from the existing single content stream.
        for item in session.execute(
            select(Item).where(
                Item.collection_id == collection_id,
                Item.deleted_at.is_(None),
            )
        ).scalars():
            item.version += 1
            item.content_seq = next_sequence(session)
            item.updated_at = now
