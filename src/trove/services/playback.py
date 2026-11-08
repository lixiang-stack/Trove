from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from trove.clock import utc_ms
from trove.content_package import ContentPackage
from trove.db.models import Artifact, BookChapter, Item, TranscriptSegment
from trove.domain.items import ConsumptionState
from trove.errors import NotFoundError, ValidationError
from trove.services.library import ItemBundle, LibraryService

AUTO_START_MAX_SECONDS = 5.0
AUTO_FINISH_RATIO = 0.95


class PlaybackService:
    def __init__(
        self, sessions: sessionmaker, package: ContentPackage, library: LibraryService
    ) -> None:
        self.sessions = sessions
        self.package = package
        self.library = library

    def audio_artifact(self, item_id: str) -> Artifact:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("内容不存在")
            artifact = session.execute(
                select(Artifact).where(Artifact.item_id == item_id, Artifact.kind == "audio")
            ).scalars().first()
            if artifact is None:
                raise NotFoundError("音频尚未生成")
            return artifact

    def audio_path(self, item_id: str) -> Path:
        artifact = self.audio_artifact(item_id)
        try:
            path = self.package.artifact_path(item_id, artifact.path)
        except FileNotFoundError as exc:
            raise NotFoundError("音频文件不存在") from exc
        if not path.is_file():
            raise NotFoundError("音频文件不存在")
        return path

    def update_progress(
        self,
        item_id: str,
        *,
        position_sec: float,
        consumption_state: str | None = None,
    ) -> ItemBundle:
        if position_sec < 0:
            raise ValidationError("播放位置不能为负数", details={"code": "progress.invalid"})
        if consumption_state is not None and consumption_state not in {
            ConsumptionState.UNSTARTED,
            ConsumptionState.IN_PROGRESS,
            ConsumptionState.FINISHED,
        }:
            raise ValidationError(
                "Consumption State 无效", details={"code": "progress.invalid_state"}
            )
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("内容不存在")
            duration = item.duration_sec
            position = float(position_sec)
            if duration and duration > 0:
                position = min(position, duration)
            item.audio_position_sec = position
            if consumption_state is not None:
                item.consumption_state = consumption_state
            elif duration and duration > 0:
                if position >= duration * AUTO_FINISH_RATIO:
                    item.consumption_state = ConsumptionState.FINISHED
                elif position >= min(AUTO_START_MAX_SECONDS, max(duration * 0.02, 1.0)):
                    item.consumption_state = ConsumptionState.IN_PROGRESS
            elif position > 0:
                item.consumption_state = ConsumptionState.IN_PROGRESS
            item.updated_at = utc_ms()
            session.commit()
            return self.library.get(item_id)

    def set_consumption_state(self, item_id: str, state: str) -> ItemBundle:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("内容不存在")
            item.consumption_state = state
            item.updated_at = utc_ms()
            session.commit()
        return self.library.get(item_id)

    def transcript(self, item_id: str) -> list[dict[str, Any]]:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("内容不存在")
            segments = list(
                session.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.item_id == item_id)
                    .order_by(TranscriptSegment.seq)
                ).scalars()
            )
            return [
                {
                    "seq": segment.seq,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "text": segment.text,
                }
                for segment in segments
            ]

    def chapter(self, item_id: str, chapter_index: int) -> dict[str, Any]:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("内容不存在")
            chapter = session.execute(
                select(BookChapter).where(
                    BookChapter.item_id == item_id,
                    BookChapter.chapter_index == chapter_index,
                )
            ).scalars().first()
            if chapter is None:
                raise NotFoundError("章节不存在")
            return {
                "item_id": item_id,
                "chapter_index": chapter.chapter_index,
                "title": chapter.title,
                "html": chapter.html,
                "text": chapter.text,
            }
