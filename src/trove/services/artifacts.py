from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from trove.content_package import ArtifactKind, ContentPackage, sha256_file
from trove.db.models import Artifact, Item


class ArtifactStore:
    def __init__(self, package: ContentPackage) -> None:
        self.package = package

    def install(
        self,
        session: Session,
        item: Item,
        *,
        kind: ArtifactKind,
        temp_path: Path,
        extension: str | None = None,
        mime: str | None,
        duration: float | None,
    ) -> Artifact:
        previous = self.get(session, item.id, kind)
        installed = self.package.install_artifact(
            item.id,
            kind,
            temp_path,
            extension=extension,
            mime=mime,
            replaces=previous.path if previous is not None else None,
        )
        return self._record(
            session,
            item,
            kind=installed.kind,
            relative=installed.relative_path,
            checksum=installed.sha256,
            size=installed.size,
            mime=installed.mime,
            duration=duration,
        )

    def record_document(
        self, session: Session, item: Item, *, kind: ArtifactKind, path: Path
    ) -> Artifact:
        return self._record(
            session,
            item,
            kind=kind,
            relative=path.name,
            checksum=sha256_file(path),
            size=path.stat().st_size,
            mime="application/json",
            duration=None,
        )

    def get(self, session: Session, item_id: str, kind: ArtifactKind) -> Artifact | None:
        return session.execute(
            select(Artifact).where(Artifact.item_id == item_id, Artifact.kind == kind)
        ).scalars().first()

    def remove(self, session: Session, item_id: str, kind: ArtifactKind) -> None:
        artifact = self.get(session, item_id, kind)
        if artifact is not None:
            self.package.remove_artifact(item_id, artifact.path)
            session.delete(artifact)

    def _record(
        self,
        session: Session,
        item: Item,
        *,
        kind: ArtifactKind,
        relative: str,
        checksum: str,
        size: int,
        mime: str,
        duration: float | None,
    ) -> Artifact:
        artifact = self.get(session, item.id, kind)
        if artifact is None:
            artifact = Artifact(
                item_id=item.id,
                kind=kind,
                path=relative,
                sha256=checksum,
                size=size,
                mime=mime,
                duration_sec=duration,
            )
            session.add(artifact)
        else:
            artifact.path = relative
            artifact.sha256 = checksum
            artifact.size = size
            artifact.mime = mime
            artifact.duration_sec = duration
        session.flush()
        return artifact
