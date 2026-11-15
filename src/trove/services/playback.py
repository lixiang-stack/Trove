from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from trove.clock import utc_ms
from trove.content_package import ContentPackage, sha256_file
from trove.db.models import Artifact, Item
from trove.errors import NotFoundError, ValidationError
from trove.ports import SearchIndex
from trove.services.library import LibraryService


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
            if item is None or item.deleted_at is not None:
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

    def transcript(self, item_id: str) -> list[dict[str, Any]]:
        with self.sessions() as session:
            item = session.get(Item, item_id)
            if item is None or item.deleted_at is not None:
                raise NotFoundError("Content not found")
        document = self.package.read_transcript(item_id)
        if document is None:
            return []
        return [
            {
                "seq": segment.seq,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "text": segment.text,
            }
            for segment in sorted(document.segments, key=lambda segment: segment.seq)
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
            if item is None or item.deleted_at is not None:
                raise NotFoundError("Content not found")
            document = self.package.read_transcript(item_id)
            if document is None:
                return 0, None
            segments = sorted(document.segments, key=lambda segment: segment.seq)
            changed = [segment for segment in segments if keyword in segment.text]
            if not changed:
                return 0, None
            for segment in changed:
                segment.text = segment.text.replace(keyword, new)
            document.language = document.language or item.language
            path = self.package.write_transcript(item_id, document)
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
