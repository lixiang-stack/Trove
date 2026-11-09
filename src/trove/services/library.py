from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import ColumnElement, case, false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from trove.clock import utc_ms
from trove.content_package import ContentPackage
from trove.db.models import Artifact, Item, ItemTag, Run, RunStep, Tag
from trove.domain.items import (
    ACTIVE_RUN_STATES,
    CONSUMPTION_LABELS,
    PLATFORM_LABELS,
    SOURCE_TYPE_LABELS,
    STAGE_LABELS,
    ConsumptionState,
    RunState,
)
from trove.domain.tags import normalize_tag
from trove.errors import ConflictError, NotFoundError, TroveError
from trove.logging_setup import tail_run_log
from trove.ports import SearchIndex


@dataclass(slots=True)
class ItemBundle:
    item: Item
    tags: list[Tag]
    run: Run | None
    steps: list[RunStep]
    artifacts: list[Artifact]

    @property
    def audio_artifact(self) -> Artifact | None:
        return next((artifact for artifact in self.artifacts if artifact.kind == "audio"), None)

    @property
    def book_artifact(self) -> Artifact | None:
        return next((artifact for artifact in self.artifacts if artifact.kind == "book"), None)

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
            return "处理失败"
        if state == RunState.CANCELLED:
            return "已取消"
        return "已完成"


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
    tags = list(
        session.execute(
            select(Tag)
            .join(ItemTag, ItemTag.tag_id == Tag.id)
            .where(ItemTag.item_id == item.id)
            .order_by(Tag.normalized_name)
        ).scalars()
    )
    artifacts = list(
        session.execute(select(Artifact).where(Artifact.item_id == item.id)).scalars()
    )
    return ItemBundle(item=item, tags=tags, run=run, steps=steps, artifacts=artifacts)


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
            title=title or "未命名内容",
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
                item.id, self._source_document(item, extra=extra_source)
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
                raise ConflictError("内容已存在") from exc
            return item_bundle(session, item), False

    def get(self, item_id: str) -> ItemBundle:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("内容不存在")
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
                item_type=item_type, consumption=consumption, platform=platform, tag=tag
            ):
                statement = statement.where(condition)
            if sort == "recent_consumed":
                activity = case(
                    (
                        or_(
                            Item.consumption_state != ConsumptionState.UNSTARTED,
                            Item.audio_position_sec > 0,
                        ),
                        Item.updated_at,
                    ),
                    else_=Item.created_at,
                )
                statement = statement.order_by(activity.desc(), Item.id.desc())
            else:
                statement = statement.order_by(Item.created_at.desc(), Item.id.desc())
            if limit is not None:
                statement = statement.limit(limit)
            items = session.scalars(statement).all()
            bundles = [item_bundle(session, item) for item in items]
        if not states:
            return bundles
        return [bundle for bundle in bundles if _matches_states(bundle, states)]

    def filtered_item_ids(
        self,
        *,
        item_type: str | None = None,
        consumption: str | None = None,
        platform: str | None = None,
        tag: str | None = None,
    ) -> set[str]:
        with self.sessions() as session:
            statement = select(Item.id)
            for condition in self._filter_conditions(
                item_type=item_type, consumption=consumption, platform=platform, tag=tag
            ):
                statement = statement.where(condition)
            return {str(item_id) for item_id in session.execute(statement).scalars()}

    @staticmethod
    def _filter_conditions(
        *,
        item_type: str | None = None,
        consumption: str | None = None,
        platform: str | None = None,
        tag: str | None = None,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = []
        if item_type:
            conditions.append(Item.source_type == item_type)
        if consumption:
            conditions.append(Item.consumption_state == consumption)
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

    def source_document(self, item_id: str) -> dict[str, Any]:
        return self.package.read_source(item_id)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def update_metadata(
        self, item_id: str, *, title: str | None, author: str | None
    ) -> ItemBundle:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("内容不存在")
            if title is not None:
                title = title.strip()
                if not title:
                    raise ConflictError("标题不能为空")
                item.title = title
            if author is not None:
                item.author = author.strip() or None
            item.updated_at = utc_ms()
            self.package.write_source(item.id, self._updated_source_document(item))
            session.commit()
            bundle = item_bundle(session, item)
        self.search_index.index_item(item_id)
        return bundle

    def delete(self, item_id: str) -> None:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("内容不存在")
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
            "consumption_state": item.consumption_state,
            "consumption_label": CONSUMPTION_LABELS.get(
                item.consumption_state, item.consumption_state
            ),
            "audio_position_sec": item.audio_position_sec,
            "book_locator": item.book_locator,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "processing_state": bundle.run_state,
            "processing_label": bundle.processing_label,
            "status_category": bundle.status_category,
            "has_audio": bundle.audio_artifact is not None,
            "has_book": bundle.book_artifact is not None,
            "audio_url": f"/api/items/{item.id}/audio" if bundle.audio_artifact else None,
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

    def _updated_source_document(self, item: Item) -> dict[str, Any]:
        document = self.package.read_source(item.id)
        document.update(
            {
                "title": item.title,
                "author": item.author,
                "published_at": item.published_at,
                "fetched_at": item.fetched_at,
                "language": item.language,
                "duration_sec": item.duration_sec,
                "source_path": item.source_path,
                "source_url_raw": item.source_url_raw,
                "source_url_canonical": item.source_url_canonical,
            }
        )
        return document

    def _source_document(
        self, item: Item, *, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        document: dict[str, Any] = {
            "id": item.id,
            "source_key": item.source_key,
            "source_type": item.source_type,
            "platform": item.platform,
            "source_url_raw": item.source_url_raw,
            "source_url_canonical": item.source_url_canonical,
            "source_path": item.source_path,
            "title": item.title,
            "author": item.author,
            "published_at": item.published_at,
            "fetched_at": item.fetched_at,
            "language": item.language,
            "duration_sec": item.duration_sec,
        }
        if extra:
            document.update(extra)
        return document


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
        } and bundle.item.consumption_state == state:
            return True
    return False
