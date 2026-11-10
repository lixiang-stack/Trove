from __future__ import annotations

import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from trove.config import Config
from trove.content_package import ArtifactKind, ContentPackage
from trove.db.models import Artifact, Item, ItemTag, Tag
from trove.domain.items import PLATFORM_LABELS, SOURCE_TYPE_LABELS
from trove.errors import NotFoundError

EXPORT_ARTIFACT_KINDS = (
    ArtifactKind.AUDIO,
    ArtifactKind.TRANSCRIPT,
    ArtifactKind.BOOK,
    ArtifactKind.BOOK_JSON,
    ArtifactKind.AI,
    ArtifactKind.COVER,
)


class ExportService:
    def __init__(
        self,
        config: Config,
        sessions: sessionmaker[Session],
        package: ContentPackage,
    ) -> None:
        self.config = config
        self.sessions = sessions
        self.package = package

    def create(self, item_ids: list[str] | None = None) -> tuple[Path, str]:
        items = self._load_items(item_ids)
        exports_dir = self.config.cache_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        exports_dir.chmod(0o700)
        filename = (
            f"trove-export-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
            f"-{os.urandom(3).hex()}.zip"
        )
        temporary = exports_dir / f".{filename}.tmp"
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
            ) as archive:
                index = self._write_items(archive, items)
                archive.writestr("index.md", index.encode("utf-8"))
            os.replace(temporary, exports_dir / filename)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return exports_dir / filename, filename

    def _load_items(self, item_ids: list[str] | None) -> list[Item]:
        with self.sessions() as session:
            if item_ids is None:
                return list(
                    session.execute(
                        select(Item).order_by(Item.created_at, Item.id)
                    ).scalars()
                )
            if not item_ids:
                return []
            unique_ids = list(dict.fromkeys(item_ids))
            items = list(
                session.execute(select(Item).where(Item.id.in_(unique_ids))).scalars()
            )
            found = {item.id for item in items}
            missing = [item_id for item_id in unique_ids if item_id not in found]
            if missing:
                raise NotFoundError(
                    "Export item not found",
                    details={"code": "export.unknown_item", "item_ids": missing},
                )
            by_id = {item.id: item for item in items}
            return [by_id[item_id] for item_id in unique_ids]

    def _write_items(self, archive: zipfile.ZipFile, items: list[Item]) -> str:
        sections: list[str] = []
        for item in items:
            folder = f"items/{item.id}"
            files: list[str] = []
            artifacts = self._artifacts(item.id)
            for path, name in self.package.export_files(
                item.id, [artifact.path for artifact in artifacts]
            ):
                archive.write(path, f"{folder}/{name}")
                files.append(name)
            sections.append(self._item_markdown(item, files))
        exported_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        header = [
            "# Trove Export",
            "",
            f"- Exported: {exported_at}",
            f"- Items: {len(items)}",
            "- Note: Items still processing are exported with the files available now.",
            "",
        ]
        return "\n".join(header + sections)

    def _artifacts(self, item_id: str) -> list[Artifact]:
        with self.sessions() as session:
            return list(
                session.execute(
                    select(Artifact)
                    .where(
                        Artifact.item_id == item_id,
                        Artifact.kind.in_(EXPORT_ARTIFACT_KINDS),
                    )
                    .order_by(Artifact.id)
                ).scalars()
            )

    def _item_markdown(self, item: Item, files: list[str]) -> str:
        with self.sessions() as session:
            tags = list(
                session.execute(
                    select(Tag.name)
                    .join(ItemTag, ItemTag.tag_id == Tag.id)
                    .where(ItemTag.item_id == item.id)
                    .order_by(Tag.normalized_name)
                ).scalars()
            )
        source = (
            item.source_url_raw
            or item.source_url_canonical
            or item.source_path
            or "(unknown)"
        )
        added = datetime.fromtimestamp(item.created_at / 1000, tz=UTC).strftime("%Y-%m-%d")
        lines = [
            f"## {item.title}",
            "",
            f"- Type: {SOURCE_TYPE_LABELS.get(item.source_type, item.source_type)}"
            f" / {PLATFORM_LABELS.get(item.platform, item.platform)}",
            f"- Source: {source}",
            f"- Author: {item.author or 'Unknown'}",
            f"- Published: {item.published_at or '—'}",
            f"- Added: {added}",
            f"- Summary: {item.summary or '—'}",
            f"- Tags: {', '.join(str(tag) for tag in tags) or '—'}",
            "- Files:",
        ]
        lines.extend(f"  - [{name}](items/{item.id}/{name})" for name in files)
        lines.append("")
        return "\n".join(lines)
