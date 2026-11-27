from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.config import Config
from trove.content_package import ContentPackage
from trove.db.models import Item, SyncFieldClock, SyncMutation, SyncSequence
from trove.domain.items import (
    ConsumptionState,
    derive_audio_consumption_state,
    derive_reading_consumption_state,
)
from trove.domain.reading import BookLocator, parse_book_locator, serialize_book_locator
from trove.domain.sync import (
    AUDIO_PROGRESS,
    BOOK_PROGRESS,
    CONSUMPTION_STATE,
    HOST_WEB_DEVICE,
    TAGS,
    FieldClock,
    normalize_client_time,
    parse_cursor,
    wins,
)
from trove.domain.tags import normalize_tag
from trove.errors import NotFoundError, ValidationError
from trove.services.library import LibraryService, item_bundle

MUTATION_TTL_MS = 24 * 60 * 60 * 1000


class SyncService:
    def __init__(
        self,
        config: Config,
        sessions: sessionmaker[Session],
        package: ContentPackage,
        library: LibraryService,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package
        self.library = library

    def manifest(self, *, cursor: str | None, limit: int) -> dict[str, Any]:
        with self.sessions() as session:
            sequence = session.get(SyncSequence, 1)
            assert sequence is not None
            parsed = parse_cursor(cursor, max_value=sequence.value)
            rows = list(
                session.execute(
                    select(Item)
                    .where(Item.content_seq > parsed)
                    .order_by(Item.content_seq, Item.id)
                    .limit(limit + 1)
                ).scalars()
            )
            has_more = len(rows) > limit
            page = rows[:limit]
            items: list[dict[str, Any]] = []
            tombstones: list[dict[str, Any]] = []
            for item in page:
                if item.deleted_at is not None:
                    tombstones.append(
                        {
                            "id": item.id,
                            "version": item.version,
                            "deleted_at": item.deleted_at,
                            "epoch": sequence.epoch,
                        }
                    )
                else:
                    items.append(self._compact_item(session, item))
            next_cursor = page[-1].content_seq if page else parsed
            return {
                "items": items,
                "tombstones": tombstones,
                "next_cursor": str(next_cursor),
                "has_more": has_more,
                "epoch": sequence.epoch,
            }

    def state(self, *, cursor: str | None, limit: int) -> dict[str, Any]:
        with self.sessions() as session:
            sequence = session.get(SyncSequence, 1)
            assert sequence is not None
            parsed = parse_cursor(cursor, max_value=sequence.value)
            rows = list(
                session.execute(
                    select(Item)
                    .where(
                        Item.state_seq > parsed,
                        Item.deleted_at.is_(None),
                    )
                    .order_by(Item.state_seq, Item.id)
                    .limit(limit + 1)
                ).scalars()
            )
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = page[-1].state_seq if page else parsed
            return {
                "items": [
                    {
                        "id": item.id,
                        "state_seq": item.state_seq,
                        "audio_position_sec": item.audio_position_sec,
                        "book_locator": item.book_locator,
                        "consumption_state": item.consumption_state,
                        "last_consumed_at": item.last_consumed_at,
                    }
                    for item in page
                ],
                "next_cursor": str(next_cursor),
                "has_more": has_more,
                "epoch": sequence.epoch,
            }

    def apply_progress(
        self,
        item_id: str,
        *,
        position_sec: float | None,
        book_locator: BookLocator | None,
        consumption_state: str | None,
        client_updated_at: int | None,
        device_id: str,
        idempotency_key: str | None = None,
        require_progress: bool = True,
    ) -> dict[str, Any]:
        self._validate_progress(
            item_id,
            position_sec=position_sec,
            book_locator=book_locator,
            consumption_state=consumption_state,
            require_progress=require_progress,
        )
        now = utc_ms()
        client_time, skew = normalize_client_time(client_updated_at, now)
        clock = FieldClock(client_updated_at=client_time, device_id=device_id)
        with self.sessions() as session:
            cached = self._cached_mutation(session, device_id, idempotency_key)
            if cached is not None:
                return cached
            item = self._require_item(session, item_id)
            clocks = self._clocks(session, item_id)
            requested = self._requested_fields(
                position_sec=position_sec,
                book_locator=book_locator,
                consumption_state=consumption_state,
                clock=clock,
            )
            winners = {
                field
                for field, candidate in requested.items()
                if wins(candidate, clocks.get(field))
            }
            applied = len(winners) == len(requested)
            self._apply_progress_winners(
                session,
                item,
                clocks,
                winners=winners,
                position_sec=position_sec,
                book_locator=book_locator,
                consumption_state=consumption_state,
                clock=clock,
                now=now,
            )
            response = self._mutation_response(
                session,
                item,
                applied=applied,
                clocks=clocks,
                warnings=["sync.clock_skew"] if skew else [],
            )
            self._store_mutation(session, device_id, idempotency_key, response, now)
            session.commit()
            return response

    def _validate_progress(
        self,
        item_id: str,
        *,
        position_sec: float | None,
        book_locator: BookLocator | None,
        consumption_state: str | None,
        require_progress: bool,
    ) -> None:
        if require_progress and position_sec is None and book_locator is None:
            raise ValidationError(
                "Missing progress position", details={"code": "progress.missing"}
            )
        if consumption_state is not None and consumption_state not in {
            ConsumptionState.UNSTARTED,
            ConsumptionState.IN_PROGRESS,
            ConsumptionState.FINISHED,
        }:
            raise ValidationError(
                "Invalid consumption state", details={"code": "progress.invalid_state"}
            )
        if book_locator is not None:
            self._validate_locator(item_id, book_locator)

    @staticmethod
    def _requested_fields(
        *,
        position_sec: float | None,
        book_locator: BookLocator | None,
        consumption_state: str | None,
        clock: FieldClock,
    ) -> dict[str, FieldClock]:
        requested: dict[str, FieldClock] = {}
        if position_sec is not None:
            requested[AUDIO_PROGRESS] = clock
        if book_locator is not None:
            requested[BOOK_PROGRESS] = clock
        if consumption_state is not None:
            requested[CONSUMPTION_STATE] = clock
        return requested

    def _apply_progress_winners(
        self,
        session: Session,
        item: Item,
        clocks: dict[str, FieldClock],
        *,
        winners: set[str],
        position_sec: float | None,
        book_locator: BookLocator | None,
        consumption_state: str | None,
        clock: FieldClock,
        now: int,
    ) -> None:
        if AUDIO_PROGRESS in winners:
            position = float(position_sec or 0.0)
            duration = item.duration_sec
            if duration and duration > 0:
                position = min(position, duration)
            item.audio_position_sec = position
            self._write_clock(session, clocks, item.id, AUDIO_PROGRESS, clock)
        if BOOK_PROGRESS in winners and book_locator is not None:
            item.book_locator = serialize_book_locator(book_locator)
            self._write_clock(session, clocks, item.id, BOOK_PROGRESS, clock)
        if CONSUMPTION_STATE in winners and consumption_state is not None:
            item.consumption_state = consumption_state
            self._write_clock(session, clocks, item.id, CONSUMPTION_STATE, clock)
        elif AUDIO_PROGRESS in winners or BOOK_PROGRESS in winners:
            self._derive_consumption_state(
                session, clocks, item, clock, audio=bool(AUDIO_PROGRESS in winners)
            )
        if winners:
            item.last_consumed_at = now
            item.updated_at = now

    def apply_consumption_state(
        self,
        item_id: str,
        *,
        consumption_state: str,
        device_id: str = HOST_WEB_DEVICE,
        client_updated_at: int | None = None,
    ) -> dict[str, Any]:
        return self.apply_progress(
            item_id,
            position_sec=None,
            book_locator=None,
            consumption_state=consumption_state,
            client_updated_at=client_updated_at,
            device_id=device_id,
            require_progress=False,
        )

    def apply_tags(
        self,
        item_id: str,
        *,
        tags: list[str],
        client_updated_at: int | None,
        device_id: str,
        idempotency_key: str | None = None,
        mark_all_user: bool = True,
    ) -> dict[str, Any]:
        now = utc_ms()
        client_time, skew = normalize_client_time(client_updated_at, now)
        clock = FieldClock(client_updated_at=client_time, device_id=device_id)
        with self.sessions() as session:
            cached = self._cached_mutation(session, device_id, idempotency_key)
            if cached is not None:
                return cached
            item = self._require_item(session, item_id)
            clocks = self._clocks(session, item_id)
            applied = wins(clock, clocks.get(TAGS))
            if applied:
                self.library.replace_tags_in_session(
                    session, item, tags, mark_all_user=mark_all_user
                )
                item.updated_at = now
                self._write_clock(session, clocks, item_id, TAGS, clock)
            response = self._mutation_response(
                session,
                item,
                applied=applied,
                clocks=clocks,
                warnings=["sync.clock_skew"] if skew else [],
            )
            self._store_mutation(session, device_id, idempotency_key, response, now)
            session.commit()
        if applied:
            self.library.search_index.index_item(item_id)
        return response

    def replace_tags(
        self,
        item_id: str,
        *,
        tags: list[str],
        device_id: str,
        client_updated_at: int | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self.apply_tags(
            item_id,
            tags=tags,
            client_updated_at=client_updated_at,
            device_id=device_id,
            idempotency_key=idempotency_key,
            mark_all_user=True,
        )

    def add_tag(
        self,
        item_id: str,
        raw: str,
        *,
        device_id: str,
        client_updated_at: int | None = None,
    ) -> dict[str, Any]:
        bundle = self.library.get(item_id)
        return self.apply_tags(
            item_id,
            tags=[tag.name for tag in bundle.tags] + [raw],
            client_updated_at=client_updated_at,
            device_id=device_id,
            mark_all_user=False,
        )

    def remove_tag(
        self,
        item_id: str,
        raw: str,
        *,
        device_id: str,
        client_updated_at: int | None = None,
    ) -> dict[str, Any]:
        bundle = self.library.get(item_id)
        _, normalized = normalize_tag(raw)
        remaining = [
            tag.name for tag in bundle.tags if tag.normalized_name != normalized
        ]
        if len(remaining) == len(bundle.tags):
            raise NotFoundError(
                "Tag not found", details={"code": "tag.not_found"}
            )
        return self.apply_tags(
            item_id,
            tags=remaining,
            client_updated_at=client_updated_at,
            device_id=device_id,
            mark_all_user=False,
        )

    def _validate_locator(self, item_id: str, locator: BookLocator) -> None:
        document = self.package.read_book(item_id)
        chapter = (
            next(
                (
                    candidate
                    for candidate in document.chapters
                    if candidate.chapter_index == locator.chapter_index
                ),
                None,
            )
            if document is not None
            else None
        )
        if chapter is None:
            raise ValidationError(
                "Chapter not found", details={"code": "book.chapter_not_found"}
            )

    def _derive_consumption_state(
        self,
        session: Session,
        clocks: dict[str, FieldClock],
        item: Item,
        clock: FieldClock,
        *,
        audio: bool,
    ) -> None:
        derived = item.consumption_state
        if audio:
            derived = derive_audio_consumption_state(
                derived,
                position=item.audio_position_sec,
                duration=item.duration_sec,
            )
        if item.book_locator is not None:
            locator = parse_book_locator(item.book_locator)
            has_progress = locator is not None and (
                locator.chapter_index > 0
                or (locator.paragraph_index or 0) > 0
                or locator.scroll_ratio > 0.001
            )
            derived = derive_reading_consumption_state(
                derived, has_progress=has_progress
            )
        if wins(clock, clocks.get(CONSUMPTION_STATE)):
            item.consumption_state = derived
            self._write_clock(session, clocks, item.id, CONSUMPTION_STATE, clock)

    @staticmethod
    def _require_item(session: Session, item_id: str) -> Item:
        item = session.get(Item, item_id)
        if item is None or item.deleted_at is not None:
            raise NotFoundError("Content not found")
        return item

    @staticmethod
    def _clocks(session: Session, item_id: str) -> dict[str, FieldClock]:
        rows = session.execute(
            select(SyncFieldClock).where(SyncFieldClock.item_id == item_id)
        ).scalars()
        return {
            row.field: FieldClock(
                client_updated_at=row.client_updated_at, device_id=row.device_id
            )
            for row in rows
        }

    @staticmethod
    def _write_clock(
        session: Session,
        clocks: dict[str, FieldClock],
        item_id: str,
        field: str,
        clock: FieldClock,
    ) -> None:
        row = session.get(SyncFieldClock, (item_id, field))
        if row is None:
            session.add(
                SyncFieldClock(
                    item_id=item_id,
                    field=field,
                    client_updated_at=clock.client_updated_at,
                    device_id=clock.device_id,
                )
            )
        else:
            row.client_updated_at = clock.client_updated_at
            row.device_id = clock.device_id
        clocks[field] = clock

    @staticmethod
    def _cached_mutation(
        session: Session, device_id: str, idempotency_key: str | None
    ) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        row = session.get(SyncMutation, (device_id, idempotency_key))
        if row is None:
            return None
        return json.loads(row.response_json)

    @staticmethod
    def _store_mutation(
        session: Session,
        device_id: str,
        idempotency_key: str | None,
        response: dict[str, Any],
        now: int,
    ) -> None:
        if not idempotency_key:
            return
        session.execute(
            delete(SyncMutation).where(SyncMutation.created_at < now - MUTATION_TTL_MS)
        )
        session.add(
            SyncMutation(
                device_id=device_id,
                mutation_id=idempotency_key,
                response_json=json.dumps(response, ensure_ascii=False),
                created_at=now,
            )
        )

    def _mutation_response(
        self,
        session: Session,
        item: Item,
        *,
        applied: bool,
        clocks: dict[str, FieldClock],
        warnings: list[str],
    ) -> dict[str, Any]:
        bundle = item_bundle(session, item)
        return {
            "ok": True,
            "applied": applied,
            "item": self.library.payload(bundle),
            "field_clocks": {
                field: {
                    "client_updated_at": clock.client_updated_at,
                    "device_id": clock.device_id,
                }
                for field, clock in sorted(clocks.items())
            },
            "warnings": warnings,
        }

    def _compact_item(self, session: Session, item: Item) -> dict[str, Any]:
        bundle = item_bundle(session, item)
        run = bundle.run
        return {
            "id": item.id,
            "version": item.version,
            "source_type": item.source_type,
            "platform": item.platform,
            "source_url_raw": item.source_url_raw,
            "collection_id": item.collection_id,
            "collection_index": item.collection_index,
            "collection_title": (
                bundle.collection.title if bundle.collection is not None else None
            ),
            "collection_platform": (
                bundle.collection.platform if bundle.collection is not None else None
            ),
            "collection_source_url": (
                bundle.collection.source_url_canonical
                if bundle.collection is not None
                else None
            ),
            "title": item.title,
            "author": item.author,
            "published_at": item.published_at,
            "fetched_at": item.fetched_at,
            "language": item.language,
            "duration_sec": item.duration_sec,
            "summary": item.summary,
            "tags": [tag.name for tag in bundle.tags],
            "processing_state": bundle.run_state,
            "error_code": run.error_code if run is not None else None,
            "error_message": (
                self.library.public_text(
                    run.error_message, source_path=item.source_path
                )
                if run is not None
                else None
            ),
            "has_audio": bundle.audio_artifact is not None,
            "has_book": bundle.book_artifact is not None,
            "files": [
                {
                    "kind": artifact.kind,
                    "sha256": artifact.sha256,
                    "size": artifact.size,
                    "mime": artifact.mime,
                    "version": item.version,
                    "url": f"/api/items/{item.id}/files/{artifact.kind}",
                }
                for artifact in sorted(bundle.artifacts, key=lambda row: row.kind)
            ],
        }
