from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import ColumnElement, false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.content_package import ContentPackage
from trove.db.models import AiResult, Artifact, Item, ItemTag, Run, RunStep, Tag
from trove.domain.items import (
    ACTIVE_RUN_STATES,
    CONSUMPTION_LABELS,
    PLATFORM_LABELS,
    SOURCE_TYPE_LABELS,
    STAGE_LABELS,
    ConsumptionState,
    RunState,
)
from trove.domain.reading import parse_book_locator
from trove.domain.tags import normalize_tag
from trove.errors import ConflictError, NotFoundError, TroveError
from trove.logging_setup import tail_run_log
from trove.ports import SearchIndex
from trove.services.package_documents import source_document


def has_consumption_progress(item: Item) -> bool:
    if item.audio_position_sec > 0:
        return True
    locator = parse_book_locator(item.book_locator)
    return locator is not None and (
        locator.chapter_index > 0
        or (locator.paragraph_index or 0) > 0
        or locator.scroll_ratio > 0.001
    )


def effective_consumption_state(item: Item) -> str:
    if item.consumption_state == ConsumptionState.IN_PROGRESS and not has_consumption_progress(
        item
    ):
        return ConsumptionState.UNSTARTED
    return item.consumption_state


@dataclass(slots=True)
class ItemBundle:
    item: Item
    tags: list[Tag]
    run: Run | None
    steps: list[RunStep]
    artifacts: list[Artifact]
    ai_result: AiResult | None = None
    tag_sources: dict[int, str] = field(default_factory=dict)

    @property
    def consumption_state(self) -> str:
        return effective_consumption_state(self.item)

    @property
    def consumption_label(self) -> str:
        return CONSUMPTION_LABELS.get(self.consumption_state, self.consumption_state)

    @property
    def audio_artifact(self) -> Artifact | None:
        return next((artifact for artifact in self.artifacts if artifact.kind == "audio"), None)

    @property
    def book_artifact(self) -> Artifact | None:
        return next((artifact for artifact in self.artifacts if artifact.kind == "book"), None)

    @property
    def cover_artifact(self) -> Artifact | None:
        return next((artifact for artifact in self.artifacts if artifact.kind == "cover"), None)

    @property
    def run_state(self) -> str:
        if self.run is None:
            return RunState.COMPLETED if self.artifacts else RunState.QUEUED
        return self.run.state

    @property
    def status_category(self) -> str:
        state = self.run_state
        if state == RunState.FAILED:
            return "failed"
        if state == RunState.CANCELLED:
            return "cancelled"
        if state in ACTIVE_RUN_STATES:
            return "processing"
        return "ready"

    @property
    def processing_label(self) -> str:
        state = self.run_state
        if state in ACTIVE_RUN_STATES:
            return STAGE_LABELS.get(state, state)
        if state == RunState.FAILED:
            return "Failed"
        if state == RunState.CANCELLED:
            return "Cancelled"
        return "Completed"


@dataclass(slots=True)
class ContinueEntry:
    bundle: ItemBundle
    kind: str


def item_bundle(session: Session, item: Item) -> ItemBundle:
    run = session.execute(
        select(Run).where(Run.item_id == item.id).order_by(Run.created_at.desc(), Run.id.desc())
    ).scalars().first()
    steps = []
    if run is not None:
        steps = list(
            session.execute(
                select(RunStep)
                .where(RunStep.run_id == run.id)
                .order_by(RunStep.started_at, RunStep.id)
            ).scalars()
        )
    tag_rows = list(
        session.execute(
            select(ItemTag)
            .join(Tag, Tag.id == ItemTag.tag_id)
            .where(ItemTag.item_id == item.id)
            .order_by(Tag.normalized_name)
        ).scalars()
    )
    tags = [row.tag for row in tag_rows]
    tag_sources = {row.tag_id: row.source for row in tag_rows}
    artifacts = list(
        session.execute(select(Artifact).where(Artifact.item_id == item.id)).scalars()
    )
    ai_result = session.execute(
        select(AiResult)
        .where(AiResult.item_id == item.id)
        .order_by(AiResult.created_at.desc(), AiResult.id.desc())
    ).scalars().first()
    return ItemBundle(
        item=item,
        tags=tags,
        run=run,
        steps=steps,
        artifacts=artifacts,
        ai_result=ai_result,
        tag_sources=tag_sources,
    )


class LibraryService:
    def __init__(
        self,
        config,
        sessions: sessionmaker[Session],
        package: ContentPackage,
        search_index: SearchIndex,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package
        self.search_index = search_index

    # ------------------------------------------------------------------
    # Create and read
    # ------------------------------------------------------------------
    def create_item(
        self,
        *,
        source_key: str,
        source_type: str,
        platform: str,
        title: str,
        source_url_raw: str | None = None,
        source_url_canonical: str | None = None,
        source_path: str | None = None,
        author: str | None = None,
        published_at: str | None = None,
        language: str | None = None,
        duration_sec: float | None = None,
        extra_source: dict[str, Any] | None = None,
    ) -> tuple[ItemBundle, bool]:
        now = utc_ms()
        with self.sessions() as session:
            existing = session.execute(
                select(Item).where(Item.source_key == source_key)
            ).scalars().first()
            if existing is not None:
                return item_bundle(session, existing), True
        item = Item(
            id=str(uuid.uuid4()),
            source_key=source_key,
            source_type=source_type,
            platform=platform,
            source_url_raw=source_url_raw,
            source_url_canonical=source_url_canonical,
            source_path=source_path,
            title=title or "Untitled content",
            author=author,
            published_at=published_at,
            fetched_at=now,
            language=language,
            duration_sec=duration_sec,
            consumption_state=ConsumptionState.UNSTARTED,
            audio_position_sec=0.0,
            created_at=now,
            updated_at=now,
        )
        # The content package is the portable fact source: write it before the DB row.
        self.package.ensure(item.id)
        try:
            self.package.write_source(
                item.id, source_document(item, extra=extra_source)
            )
        except Exception:
            self.package.remove(item.id)
            raise
        with self.sessions() as session:
            session.add(item)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                self.package.remove(item.id)
                existing = session.execute(
                    select(Item).where(Item.source_key == source_key)
                ).scalars().first()
                if existing is not None:
                    return item_bundle(session, existing), True
                raise ConflictError("Content already exists") from exc
            return item_bundle(session, item), False

    def get(self, item_id: str) -> ItemBundle:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            return item_bundle(session, item)

    def list_items(
        self,
        *,
        sort: str = "recent_added",
        states: set[str] | None = None,
        item_type: str | None = None,
        consumption: str | None = None,
        platform: str | None = None,
        tag: str | None = None,
        limit: int | None = None,
    ) -> list[ItemBundle]:
        with self.sessions() as session:
            statement = select(Item)
            for condition in self._filter_conditions(
                item_type=item_type, platform=platform, tag=tag
            ):
                statement = statement.where(condition)
            if sort == "recent_consumed":
                activity = func.coalesce(Item.last_consumed_at, Item.created_at)
                statement = statement.order_by(activity.desc(), Item.id.desc())
            else:
                statement = statement.order_by(Item.created_at.desc(), Item.id.desc())
            if limit is not None:
                statement = statement.limit(limit)
            items = session.scalars(statement).all()
            bundles = [item_bundle(session, item) for item in items]
        if consumption:
            bundles = [
                bundle for bundle in bundles if bundle.consumption_state == consumption
            ]
        if not states:
            return bundles
        return [bundle for bundle in bundles if _matches_states(bundle, states)]

    def continue_items(self, *, limit: int = 20) -> list[ContinueEntry]:
        with self.sessions() as session:
            items = list(
                session.execute(
                    select(Item)
                    .where(
                        Item.consumption_state != ConsumptionState.FINISHED,
                        or_(
                            Item.audio_position_sec > 0,
                            Item.book_locator.is_not(None),
                        ),
                    )
                    .order_by(
                        func.coalesce(Item.last_consumed_at, Item.updated_at).desc(),
                        Item.id.desc(),
                    )
                    .limit(limit)
                ).scalars()
            )
            return [
                ContinueEntry(
                    bundle=item_bundle(session, item),
                    kind="read" if item.book_locator else "listen",
                )
                for item in items
                if has_consumption_progress(item)
            ]

    def filtered_item_ids(
        self,
        *,
        item_type: str | None = None,
        consumption: str | None = None,
        platform: str | None = None,
        tag: str | None = None,
    ) -> set[str]:
        with self.sessions() as session:
            statement = select(Item)
            for condition in self._filter_conditions(
                item_type=item_type, platform=platform, tag=tag
            ):
                statement = statement.where(condition)
            items = session.scalars(statement).all()
        return {
            item.id
            for item in items
            if consumption is None or effective_consumption_state(item) == consumption
        }

    @staticmethod
    def _filter_conditions(
        *,
        item_type: str | None = None,
        platform: str | None = None,
        tag: str | None = None,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if item_type:
            conditions.append(Item.source_type == item_type)
        if platform:
            conditions.append(Item.platform == platform)
        if tag:
            try:
                _, normalized = normalize_tag(tag)
            except TroveError:
                conditions.append(false())
            else:
                conditions.append(
                    Item.id.in_(
                        select(ItemTag.item_id)
                        .join(Tag, Tag.id == ItemTag.tag_id)
                        .where(Tag.normalized_name == normalized)
                    )
                )
        return conditions

    def tag_counts(self) -> list[tuple[str, int]]:
        with self.sessions() as session:
            rows = session.execute(
                select(Tag.name, func.count(ItemTag.item_id).label("count"))
                .join(ItemTag, ItemTag.tag_id == Tag.id)
                .group_by(Tag.id)
                .order_by(func.count(ItemTag.item_id).desc(), Tag.normalized_name)
            )
            return [(name, count) for name, count in rows]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def add_tag(self, item_id: str, raw: str) -> ItemBundle:
        display, normalized = normalize_tag(raw)
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            tag = session.execute(
                select(Tag).where(Tag.normalized_name == normalized)
            ).scalars().first()
            if tag is None:
                tag = Tag(name=display, normalized_name=normalized)
                session.add(tag)
                session.flush()
            row = session.get(ItemTag, (item_id, tag.id))
            if row is None:
                session.add(ItemTag(item_id=item_id, tag_id=tag.id, source="user"))
            else:
                row.source = "user"
            item.updated_at = utc_ms()
            session.commit()
            bundle = item_bundle(session, item)
        self.search_index.index_item(item_id)
        return bundle

    def replace_tags(self, item_id: str, raw_tags: list[str]) -> ItemBundle:
        normalized_tags: list[tuple[str, str]] = []
        seen: set[str] = set()
        for raw in raw_tags:
            display, normalized = normalize_tag(raw)
            if normalized in seen:
                continue
            seen.add(normalized)
            normalized_tags.append((display, normalized))
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            attached = {
                row.tag_id: row
                for row in session.execute(
                    select(ItemTag).where(ItemTag.item_id == item_id)
                ).scalars()
            }
            keep: set[int] = set()
            for display, normalized in normalized_tags:
                tag = session.execute(
                    select(Tag).where(Tag.normalized_name == normalized)
                ).scalars().first()
                if tag is None:
                    tag = Tag(name=display, normalized_name=normalized)
                    session.add(tag)
                    session.flush()
                row = attached.get(tag.id)
                if row is None:
                    session.add(ItemTag(item_id=item_id, tag_id=tag.id, source="user"))
                else:
                    row.source = "user"
                keep.add(tag.id)
            for tag_id, row in attached.items():
                if tag_id not in keep:
                    session.delete(row)
            item.updated_at = utc_ms()
            session.commit()
            bundle = item_bundle(session, item)
        self.search_index.index_item(item_id)
        return bundle

    def remove_tag(self, item_id: str, raw: str) -> ItemBundle:
        _, normalized = normalize_tag(raw)
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            tag = session.execute(
                select(Tag).where(Tag.normalized_name == normalized)
            ).scalars().first()
            row = (
                session.get(ItemTag, (item_id, tag.id)) if tag is not None else None
            )
            if row is None:
                raise NotFoundError("Tag not found", details={"code": "tag.not_found"})
            session.delete(row)
            item.updated_at = utc_ms()
            session.commit()
            bundle = item_bundle(session, item)
        self.search_index.index_item(item_id)
        return bundle

    def update_metadata(
        self, item_id: str, *, title: str | None, author: str | None
    ) -> ItemBundle:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            if title is not None:
                title = title.strip()
                if not title:
                    raise ConflictError("Title cannot be empty")
                item.title = title
            if author is not None:
                item.author = author.strip() or None
            item.updated_at = utc_ms()
            self.package.write_source(
                item.id,
                source_document(
                    item, base=self.package.read_source(item.id)
                ),
            )
            session.commit()
            bundle = item_bundle(session, item)
        self.search_index.index_item(item_id)
        return bundle

    def delete(self, item_id: str) -> None:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            source_path = Path(item.source_path) if item.source_path else None
            session.delete(item)
            session.commit()
        self.search_index.delete_item(item_id)
        self.package.remove(item_id)
        if source_path is not None and source_path.is_relative_to(self.config.uploads_dir):
            shutil.rmtree(source_path.parent, ignore_errors=True)


    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def payload(self, bundle: ItemBundle, *, include_run: bool = True) -> dict[str, Any]:
        item = bundle.item
        tags = [tag.name for tag in bundle.tags]
        payload: dict[str, Any] = {
            "id": item.id,
            "source_key": item.source_key,
            "source_type": item.source_type,
            "source_type_label": SOURCE_TYPE_LABELS.get(item.source_type, item.source_type),
            "platform": item.platform,
            "platform_label": PLATFORM_LABELS.get(item.platform, item.platform),
            "source_url_raw": item.source_url_raw,
            "source_url_canonical": item.source_url_canonical,
            "source_path": item.source_path,
            "title": item.title,
            "author": item.author,
            "published_at": item.published_at,
            "fetched_at": item.fetched_at,
            "language": item.language,
            "duration_sec": item.duration_sec,
            "summary": item.summary,
            "tags": tags,
            "tag_items": [
                {"name": tag.name, "source": bundle.tag_sources.get(tag.id, "ai")}
                for tag in bundle.tags
            ],
            "consumption_state": bundle.consumption_state,
            "consumption_label": bundle.consumption_label,
            "audio_position_sec": item.audio_position_sec,
            "book_locator": item.book_locator,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "processing_state": bundle.run_state,
            "processing_label": bundle.processing_label,
            "status_category": bundle.status_category,
            "has_audio": bundle.audio_artifact is not None,
            "has_book": bundle.book_artifact is not None,
            "has_cover": bundle.cover_artifact is not None,
            "audio_url": f"/api/items/{item.id}/audio" if bundle.audio_artifact else None,
            "cover_url": f"/api/items/{item.id}/cover" if bundle.cover_artifact else None,
            "ai": (
                {
                    "summary": bundle.ai_result.summary,
                    "model": bundle.ai_result.model,
                    "prompt_version": bundle.ai_result.prompt_version,
                    "input_tokens": bundle.ai_result.input_tokens,
                    "output_tokens": bundle.ai_result.output_tokens,
                    "cost_usd": bundle.ai_result.cost_usd,
                    "generated_at": bundle.ai_result.created_at,
                }
                if bundle.ai_result is not None
                else None
            ),
        }
        if include_run:
            payload["run"] = self.run_payload(bundle)
        return payload

    def run_payload(self, bundle: ItemBundle) -> dict[str, Any] | None:
        if bundle.run is None:
            return None
        run = bundle.run
        return {
            "id": run.id,
            "state": run.state,
            "label": STAGE_LABELS.get(run.state, run.state),
            "current_stage": run.current_stage,
            "error_code": run.error_code,
            "error_message": run.error_message,
            "cancel_requested": run.cancel_requested_at is not None,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "heartbeat_at": run.heartbeat_at,
            "steps": [
                {
                    "stage": step.stage,
                    "state": step.state,
                    "attempt": step.attempt,
                    "error_code": step.error_code,
                    "error_message": step.error_message,
                    "started_at": step.started_at,
                    "finished_at": step.finished_at,
                }
                for step in bundle.steps
            ],
            "log_tail": tail_run_log(self.config, run.id),
        }


def _matches_states(bundle: ItemBundle, states: set[str]) -> bool:
    for state in states:
        if state == "processing" and bundle.status_category == "processing":
            return True
        if state == "failed" and bundle.status_category == "failed":
            return True
        if state == "cancelled" and bundle.status_category == "cancelled":
            return True
        if state == "ready" and bundle.status_category == "ready":
            return True
        if state in {
            ConsumptionState.UNSTARTED,
            ConsumptionState.IN_PROGRESS,
            ConsumptionState.FINISHED,
        } and bundle.consumption_state == state:
            return True
    return False
