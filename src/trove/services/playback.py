from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from trove.clock import utc_ms
from trove.content_package import ContentPackage, sha256_file
from trove.db.models import Artifact, Item, TranscriptSegment
from trove.domain.items import ConsumptionState
from trove.errors import NotFoundError, ValidationError
from trove.ports import SearchIndex
from trove.services.library import ItemBundle, LibraryService

AUTO_START_MAX_SECONDS = 5.0
AUTO_FINISH_RATIO = 0.95


class PlaybackService:
    def __init__(
        self,
        sessions: sessionmaker,
        package: ContentPackage,
        library: LibraryService,
        search_index: SearchIndex,
    ) -> None:
        self.sessions = sessions
        self.package = package
        self.library = library
        self.search_index = search_index

    def audio_artifact(self, item_id: str) -> Artifact:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            artifact = session.execute(
                select(Artifact).where(Artifact.item_id == item_id, Artifact.kind == "audio")
            ).scalars().first()
            if artifact is None:
                raise NotFoundError("Audio has not been generated yet")
            return artifact

    def audio_path(self, item_id: str) -> Path:
        artifact = self.audio_artifact(item_id)
        try:
            path = self.package.artifact_path(item_id, artifact.path)
        except FileNotFoundError as exc:
            raise NotFoundError("Audio file not found") from exc
        if not path.is_file():
            raise NotFoundError("Audio file not found")
        return path

    def update_progress(
        self,
        item_id: str,
        *,
        position_sec: float,
        consumption_state: str | None = None,
    ) -> ItemBundle:
        if position_sec < 0:
            raise ValidationError(
                "Playback position cannot be negative", details={"code": "progress.invalid"}
            )
        if consumption_state is not None and consumption_state not in {
            ConsumptionState.UNSTARTED,
            ConsumptionState.IN_PROGRESS,
            ConsumptionState.FINISHED,
        }:
            raise ValidationError(
                "Invalid consumption state", details={"code": "progress.invalid_state"}
            )
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            duration = item.duration_sec
            position = float(position_sec)
            if duration and duration > 0:
                position = min(position, duration)
            item.audio_position_sec = position
            item.last_consumed_at = utc_ms()
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
        if state not in {
            ConsumptionState.UNSTARTED,
            ConsumptionState.IN_PROGRESS,
            ConsumptionState.FINISHED,
        }:
            raise ValidationError(
                "Invalid consumption state", details={"code": "progress.invalid_state"}
            )
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            item.consumption_state = state
            item.last_consumed_at = utc_ms()
            item.updated_at = utc_ms()
            session.commit()
        return self.library.get(item_id)

    def transcript(self, item_id: str) -> list[dict[str, Any]]:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
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

    def replace_transcript_text(
        self, item_id: str, *, old: str, new: str
    ) -> tuple[int, int | None]:
        keyword = old.strip()
        if not keyword:
            raise ValidationError(
                "Search keyword cannot be empty", details={"code": "transcript.keyword_required"}
            )
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None:
                raise NotFoundError("Content not found")
            segments = list(
                session.execute(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.item_id == item_id)
                    .order_by(TranscriptSegment.seq)
                ).scalars()
            )
            changed = [segment for segment in segments if keyword in segment.text]
            if not changed:
                return 0, None
            for segment in changed:
                segment.text = segment.text.replace(keyword, new)
            existing = self.package.read_json(item_id, "transcript.json")
            payload = dict(existing) if isinstance(existing, dict) else {}
            payload["language"] = payload.get("language") or item.language
            payload["segments"] = [
                {
                    "seq": segment.seq,
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "text": segment.text,
                }
                for segment in segments
            ]
            path = self.package.write_json(item_id, "transcript.json", payload)
            artifact = session.execute(
                select(Artifact).where(
                    Artifact.item_id == item_id, Artifact.kind == "transcript"
                )
            ).scalars().first()
            if artifact is not None:
                artifact.sha256 = sha256_file(path)
                artifact.size = path.stat().st_size
            item.updated_at = utc_ms()
            first_seq = changed[0].seq
            session.commit()
        self.search_index.index_item(item_id)
        return len(changed), first_seq
