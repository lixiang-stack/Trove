from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import secrets
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from trove.clock import utc_ms
from trove.config import Config
from trove.domain.items import Platform, SourceType
from trove.errors import PackageVersionError, StorageError

CHUNK_SIZE = 1024 * 1024
MANIFEST_FILENAME = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1

_FIXED_ARTIFACT_FILENAMES = {
    "transcript": "transcript.json",
    "book": "book.epub",
    "book_json": "book.json",
    "ai": "ai.json",
}
_EXTENSION_ARTIFACT_PREFIXES = {"audio": "audio", "cover": "cover"}

_SOURCE_KEYS = frozenset(
    {
        "id",
        "source_key",
        "source_type",
        "platform",
        "source_url_raw",
        "source_url_canonical",
        "source_path",
        "title",
        "author",
        "published_at",
        "fetched_at",
        "language",
        "duration_sec",
        "uploaded",
        "feed",
    }
)
_FEED_KEYS = frozenset(
    {
        "url",
        "episode_guid",
        "enclosure_url",
        "enclosure_type",
        "enclosure_size",
    }
)
_MANIFEST_ARTIFACT_KEYS = frozenset({"kind", "path", "sha256", "size", "mime"})
_MANIFEST_KEYS = frozenset(
    {"schema_version", "item_id", "created_at", "updated_at", "artifacts"}
)
_TRANSCRIPT_KEYS = frozenset({"language", "model", "segments"})
_TRANSCRIPT_SEGMENT_KEYS = frozenset({"seq", "start_ms", "end_ms", "text"})
_BOOK_KEYS = frozenset({"title", "author", "language", "cover", "chapters"})
_BOOK_COVER_KEYS = frozenset({"extension", "mime"})
_BOOK_CHAPTER_KEYS = frozenset(
    {"chapter_index", "title", "html", "text", "paragraphs"}
)
_AI_KEYS = frozenset(
    {
        "summary",
        "tags",
        "model",
        "prompt_version",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "generated_at",
    }
)


class ArtifactKind(StrEnum):
    AUDIO = "audio"
    TRANSCRIPT = "transcript"
    BOOK = "book"
    BOOK_JSON = "book_json"
    AI = "ai"
    COVER = "cover"


_ARTIFACT_KIND_ORDER = {str(kind): index for index, kind in enumerate(ArtifactKind)}


@dataclass(slots=True)
class InstalledArtifact:
    kind: ArtifactKind
    path: Path
    relative_path: str
    sha256: str
    size: int
    mime: str


@dataclass(slots=True)
class ManifestArtifact:
    kind: str
    path: str
    sha256: str
    size: int
    mime: str
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> ManifestArtifact:
        return cls(
            kind=_require_str(data, "kind"),
            path=_require_str(data, "path"),
            sha256=_require_str(data, "sha256"),
            size=_require_int(data, "size"),
            mime=_require_str(data, "mime"),
            extra=_extra_fields(data, _MANIFEST_ARTIFACT_KEYS),
        )

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "kind": self.kind,
                "path": self.path,
                "sha256": self.sha256,
                "size": self.size,
                "mime": self.mime,
            }
        )
        return data


@dataclass(slots=True)
class PackageManifest:
    schema_version: int
    item_id: str
    created_at: int
    updated_at: int
    artifacts: list[ManifestArtifact] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> PackageManifest:
        try:
            schema_version = _require_int(data, "schema_version")
            if schema_version != MANIFEST_SCHEMA_VERSION:
                raise PackageVersionError(
                    "Unsupported content package manifest schema_version "
                    f"{schema_version}; supported: {MANIFEST_SCHEMA_VERSION}"
                )
            return cls(
                schema_version=schema_version,
                item_id=_require_str(data, "item_id"),
                created_at=_require_int(data, "created_at"),
                updated_at=_require_int(data, "updated_at"),
                artifacts=[
                    ManifestArtifact.from_json(_require_mapping(artifact, "artifact"))
                    for artifact in _require_list(data, "artifacts")
                ],
                extra=_extra_fields(data, _MANIFEST_KEYS),
            )
        except PackageVersionError:
            raise
        except (TypeError, ValueError) as exc:
            raise StorageError(f"Invalid content package manifest.json: {exc}") from exc

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "schema_version": self.schema_version,
                "item_id": self.item_id,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "artifacts": [artifact.to_json() for artifact in self.artifacts],
            }
        )
        return data


@dataclass(frozen=True, slots=True)
class ManifestProblem:
    path: str
    message: str


@dataclass(slots=True)
class FeedSourceDocument:
    url: str
    episode_guid: str | None = None
    enclosure_url: str | None = None
    enclosure_type: str | None = None
    enclosure_size: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> FeedSourceDocument:
        return cls(
            url=_require_str(data, "url"),
            episode_guid=_optional_str(data, "episode_guid"),
            enclosure_url=_optional_str(data, "enclosure_url"),
            enclosure_type=_optional_str(data, "enclosure_type"),
            enclosure_size=_optional_int(data, "enclosure_size"),
            extra=_extra_fields(data, _FEED_KEYS),
        )

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "url": self.url,
                "episode_guid": self.episode_guid,
                "enclosure_url": self.enclosure_url,
                "enclosure_type": self.enclosure_type,
                "enclosure_size": self.enclosure_size,
            }
        )
        return data


@dataclass(slots=True)
class SourceDocument:
    id: str
    source_key: str
    source_type: SourceType
    platform: Platform
    title: str
    source_url_raw: str | None = None
    source_url_canonical: str | None = None
    source_path: str | None = None
    author: str | None = None
    published_at: str | None = None
    fetched_at: int | None = None
    language: str | None = None
    duration_sec: float | None = None
    uploaded: bool | None = None
    feed: FeedSourceDocument | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> SourceDocument:
        try:
            feed_data = data.get("feed")
            return cls(
                id=_require_str(data, "id"),
                source_key=_require_str(data, "source_key"),
                source_type=SourceType(_require_str(data, "source_type")),
                platform=Platform(_require_str(data, "platform")),
                title=_require_str(data, "title"),
                source_url_raw=_optional_str(data, "source_url_raw"),
                source_url_canonical=_optional_str(data, "source_url_canonical"),
                source_path=_optional_str(data, "source_path"),
                author=_optional_str(data, "author"),
                published_at=_optional_str(data, "published_at"),
                fetched_at=_optional_int(data, "fetched_at"),
                language=_optional_str(data, "language"),
                duration_sec=_optional_float(data, "duration_sec"),
                uploaded=_optional_bool(data, "uploaded"),
                feed=(
                    FeedSourceDocument.from_json(_require_mapping(feed_data, "feed"))
                    if feed_data is not None
                    else None
                ),
                extra=_extra_fields(data, _SOURCE_KEYS),
            )
        except (TypeError, ValueError) as exc:
            raise StorageError(f"Invalid content package source.json: {exc}") from exc

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "id": self.id,
                "source_key": self.source_key,
                "source_type": str(self.source_type),
                "platform": str(self.platform),
                "source_url_raw": self.source_url_raw,
                "source_url_canonical": self.source_url_canonical,
                "source_path": self.source_path,
                "title": self.title,
                "author": self.author,
                "published_at": self.published_at,
                "fetched_at": self.fetched_at,
                "language": self.language,
                "duration_sec": self.duration_sec,
            }
        )
        if self.uploaded is not None:
            data["uploaded"] = self.uploaded
        if self.feed is not None:
            data["feed"] = self.feed.to_json()
        return data


@dataclass(slots=True)
class TranscriptSegment:
    seq: int
    start_ms: int
    end_ms: int
    text: str
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> TranscriptSegment:
        return cls(
            seq=_require_int(data, "seq"),
            start_ms=_require_int(data, "start_ms"),
            end_ms=_require_int(data, "end_ms"),
            text=_require_text(data, "text"),
            extra=_extra_fields(data, _TRANSCRIPT_SEGMENT_KEYS),
        )

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "seq": self.seq,
                "start_ms": self.start_ms,
                "end_ms": self.end_ms,
                "text": self.text,
            }
        )
        return data


@dataclass(slots=True)
class TranscriptDocument:
    language: str | None = None
    model: str | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> TranscriptDocument:
        try:
            return cls(
                language=_optional_str(data, "language"),
                model=_optional_str(data, "model"),
                segments=[
                    TranscriptSegment.from_json(_require_mapping(segment, "segment"))
                    for segment in _require_list(data, "segments")
                ],
                extra=_extra_fields(data, _TRANSCRIPT_KEYS),
            )
        except (TypeError, ValueError) as exc:
            raise StorageError(f"Invalid content package transcript.json: {exc}") from exc

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "language": self.language,
                "model": self.model,
                "segments": [segment.to_json() for segment in self.segments],
            }
        )
        return data


@dataclass(slots=True)
class BookCoverDocument:
    extension: str
    mime: str
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> BookCoverDocument:
        return cls(
            extension=_require_str(data, "extension"),
            mime=_require_str(data, "mime"),
            extra=_extra_fields(data, _BOOK_COVER_KEYS),
        )

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update({"extension": self.extension, "mime": self.mime})
        return data


@dataclass(slots=True)
class BookChapterDocument:
    chapter_index: int
    title: str | None
    html: str
    text: str
    paragraphs: list[str]
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> BookChapterDocument:
        return cls(
            chapter_index=_require_int(data, "chapter_index"),
            title=_optional_str(data, "title"),
            html=_require_text(data, "html"),
            text=_require_text(data, "text"),
            paragraphs=_require_str_list(data, "paragraphs"),
            extra=_extra_fields(data, _BOOK_CHAPTER_KEYS),
        )

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "chapter_index": self.chapter_index,
                "title": self.title,
                "html": self.html,
                "text": self.text,
                "paragraphs": self.paragraphs,
            }
        )
        return data


@dataclass(slots=True)
class BookDocument:
    title: str
    author: str | None = None
    language: str | None = None
    cover: BookCoverDocument | None = None
    chapters: list[BookChapterDocument] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> BookDocument:
        try:
            cover_data = data.get("cover")
            return cls(
                title=_require_str(data, "title"),
                author=_optional_str(data, "author"),
                language=_optional_str(data, "language"),
                cover=(
                    BookCoverDocument.from_json(_require_mapping(cover_data, "cover"))
                    if cover_data is not None
                    else None
                ),
                chapters=[
                    BookChapterDocument.from_json(_require_mapping(chapter, "chapter"))
                    for chapter in _require_list(data, "chapters")
                ],
                extra=_extra_fields(data, _BOOK_KEYS),
            )
        except (TypeError, ValueError) as exc:
            raise StorageError(f"Invalid content package book.json: {exc}") from exc

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "title": self.title,
                "author": self.author,
                "language": self.language,
                "cover": self.cover.to_json() if self.cover is not None else None,
                "chapters": [chapter.to_json() for chapter in self.chapters],
            }
        )
        return data


@dataclass(slots=True)
class AiDocument:
    summary: str
    tags: list[str]
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    generated_at: int
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> AiDocument:
        try:
            return cls(
                summary=_require_text(data, "summary"),
                tags=_require_str_list(data, "tags"),
                model=_require_str(data, "model"),
                prompt_version=_require_str(data, "prompt_version"),
                input_tokens=_require_int(data, "input_tokens"),
                output_tokens=_require_int(data, "output_tokens"),
                cost_usd=_optional_float(data, "cost_usd"),
                generated_at=_require_int(data, "generated_at"),
                extra=_extra_fields(data, _AI_KEYS),
            )
        except (TypeError, ValueError) as exc:
            raise StorageError(f"Invalid content package ai.json: {exc}") from exc

    def to_json(self) -> dict[str, Any]:
        data = dict(self.extra)
        data.update(
            {
                "summary": self.summary,
                "tags": self.tags,
                "model": self.model,
                "prompt_version": self.prompt_version,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cost_usd": self.cost_usd,
                "generated_at": self.generated_at,
            }
        )
        return data


def _extra_fields(data: Mapping[str, Any], known: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in known}


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _require_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _require_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_int(data: Mapping[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_float(data: Mapping[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _optional_bool(data: Mapping[str, Any], key: str) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _require_list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _require_str_list(data: Mapping[str, Any], key: str) -> list[str]:
    values = _require_list(data, key)
    if any(not isinstance(value, str) for value in values):
        raise ValueError(f"{key} must contain only strings")
    return values


def _artifact_filename(kind: ArtifactKind, extension: str | None) -> str:
    fixed = _FIXED_ARTIFACT_FILENAMES.get(str(kind))
    if fixed is not None:
        if extension is not None:
            raise ValueError(f"{kind} does not accept an extension")
        return fixed
    prefix = _EXTENSION_ARTIFACT_PREFIXES.get(str(kind))
    if prefix is None:
        raise ValueError(f"unsupported artifact kind: {kind}")
    if extension is None:
        raise ValueError(f"{kind} requires an extension")
    suffix = extension.lower()
    if not suffix.startswith(".") or not suffix[1:].isalnum():
        raise ValueError(f"invalid artifact extension: {extension}")
    return f"{prefix}{suffix}"


class ContentPackage:
    def __init__(self, config: Config) -> None:
        self.config = config

    def _directory(self, item_id: str) -> Path:
        return self.config.library_dir / item_id

    def ensure(self, item_id: str) -> Path:
        directory = self._directory(item_id)
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        return directory

    def _source_path(self, item_id: str) -> Path:
        return self._directory(item_id) / "source.json"

    def read_manifest(self, item_id: str) -> PackageManifest | None:
        data = self._read_json(item_id, MANIFEST_FILENAME)
        if data is None:
            return None
        if not isinstance(data, dict):
            raise StorageError(
                "Invalid content package manifest.json: expected an object"
            )
        manifest = PackageManifest.from_json(data)
        if manifest.item_id != item_id:
            raise StorageError(
                f"Content package manifest item_id {manifest.item_id} "
                f"does not match {item_id}"
            )
        return manifest

    def write_manifest(self, item_id: str, document: PackageManifest) -> Path:
        return self._write_json(item_id, MANIFEST_FILENAME, document.to_json())

    def manifest_for_export(
        self,
        item_id: str,
        artifacts: Iterable[ManifestArtifact],
        *,
        created_at: int,
        updated_at: int,
    ) -> PackageManifest:
        existing = self.read_manifest(item_id)
        previous = (
            {artifact.kind: artifact.extra for artifact in existing.artifacts}
            if existing is not None
            else {}
        )
        return PackageManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            item_id=item_id,
            created_at=existing.created_at if existing is not None else created_at,
            updated_at=existing.updated_at if existing is not None else updated_at,
            artifacts=[
                replace(artifact, extra=dict(previous.get(artifact.kind, {})))
                for artifact in artifacts
            ],
            extra=dict(existing.extra) if existing is not None else {},
        )

    def _ensure_supported_manifest(self, item_id: str) -> None:
        self.read_manifest(item_id)

    def verify_manifest(self, item_id: str) -> list[ManifestProblem]:
        if not self._directory(item_id).is_dir():
            return [ManifestProblem(item_id, "content package directory is missing")]
        problems: list[ManifestProblem] = []
        if not self._source_path(item_id).is_file():
            problems.append(ManifestProblem("source.json", "file is missing"))
        manifest = self.read_manifest(item_id)
        if manifest is None:
            problems.append(ManifestProblem(MANIFEST_FILENAME, "manifest is missing"))
            return problems
        for artifact in manifest.artifacts:
            try:
                path = self.artifact_path(item_id, artifact.path)
            except FileNotFoundError:
                problems.append(ManifestProblem(artifact.path, "invalid path"))
                continue
            try:
                if not path.is_file():
                    problems.append(ManifestProblem(artifact.path, "file is missing"))
                elif path.stat().st_size != artifact.size:
                    problems.append(
                        ManifestProblem(
                            artifact.path,
                            f"size is {path.stat().st_size}, expected {artifact.size}",
                        )
                    )
                elif sha256_file(path) != artifact.sha256:
                    problems.append(ManifestProblem(artifact.path, "sha256 mismatch"))
            except OSError as exc:
                problems.append(
                    ManifestProblem(artifact.path, f"could not read file: {exc}")
                )
        return problems

    def read_source(self, item_id: str) -> SourceDocument | None:
        self._ensure_supported_manifest(item_id)
        data = self._read_document(item_id, "source.json")
        return SourceDocument.from_json(data) if data is not None else None

    def write_source(self, item_id: str, document: SourceDocument) -> Path:
        self._ensure_supported_manifest(item_id)
        path = self._write_json(item_id, "source.json", document.to_json())
        self._refresh_manifest(item_id)
        return path

    def read_transcript(self, item_id: str) -> TranscriptDocument | None:
        self._ensure_supported_manifest(item_id)
        data = self._read_document(item_id, "transcript.json")
        return TranscriptDocument.from_json(data) if data is not None else None

    def write_transcript(self, item_id: str, document: TranscriptDocument) -> Path:
        return self._write_document(
            item_id, ArtifactKind.TRANSCRIPT, "transcript.json", document.to_json()
        )

    def read_book(self, item_id: str) -> BookDocument | None:
        self._ensure_supported_manifest(item_id)
        data = self._read_document(item_id, "book.json")
        return BookDocument.from_json(data) if data is not None else None

    def write_book(self, item_id: str, document: BookDocument) -> Path:
        return self._write_document(
            item_id, ArtifactKind.BOOK_JSON, "book.json", document.to_json()
        )

    def read_ai(self, item_id: str) -> AiDocument | None:
        self._ensure_supported_manifest(item_id)
        data = self._read_document(item_id, "ai.json")
        return AiDocument.from_json(data) if data is not None else None

    def write_ai(self, item_id: str, document: AiDocument) -> Path:
        return self._write_document(
            item_id, ArtifactKind.AI, "ai.json", document.to_json()
        )

    def install_artifact(
        self,
        item_id: str,
        kind: ArtifactKind,
        temp_path: Path,
        *,
        extension: str | None = None,
        mime: str | None = None,
        replaces: str | None = None,
    ) -> InstalledArtifact:
        filename = _artifact_filename(kind, extension)
        self._ensure_supported_manifest(item_id)
        self._validate_replacement(item_id, replaces, filename)
        destination, checksum, size = self._install_temp(item_id, temp_path, filename)
        self._remove_replaced(item_id, replaces, filename)
        installed_mime = mime or guess_mime(filename)
        self._refresh_manifest(
            item_id,
            changed=self._manifest_artifact(
                kind, filename, checksum=checksum, size=size, mime=installed_mime
            ),
        )
        return InstalledArtifact(
            kind=kind,
            path=destination,
            relative_path=filename,
            sha256=checksum,
            size=size,
            mime=installed_mime,
        )

    def copy_artifact(
        self,
        item_id: str,
        kind: ArtifactKind,
        source: Path,
        *,
        extension: str | None = None,
        mime: str | None = None,
        replaces: str | None = None,
    ) -> InstalledArtifact:
        filename = _artifact_filename(kind, extension)
        self._ensure_supported_manifest(item_id)
        self._validate_replacement(item_id, replaces, filename)
        destination, checksum, size = self._copy_in(item_id, source, filename)
        self._remove_replaced(item_id, replaces, filename)
        installed_mime = mime or guess_mime(filename)
        self._refresh_manifest(
            item_id,
            changed=self._manifest_artifact(
                kind, filename, checksum=checksum, size=size, mime=installed_mime
            ),
        )
        return InstalledArtifact(
            kind=kind,
            path=destination,
            relative_path=filename,
            sha256=checksum,
            size=size,
            mime=installed_mime,
        )

    def remove_artifact(self, item_id: str, relative: str) -> None:
        self._ensure_supported_manifest(item_id)
        self.artifact_path(item_id, relative).unlink(missing_ok=True)
        self._refresh_manifest(item_id, removed_path=relative)

    def export_files(
        self, item_id: str, artifact_paths: Iterable[str]
    ) -> list[tuple[Path, str]]:
        self._ensure_supported_manifest(item_id)
        source = self._source_path(item_id)
        if not source.is_file():
            raise StorageError("Content package file is missing: source.json")
        files = [(source, "source.json")]
        for relative in artifact_paths:
            try:
                path = self.artifact_path(item_id, relative)
            except FileNotFoundError as exc:
                raise StorageError(
                    f"Content package file is missing: {relative}"
                ) from exc
            if not path.is_file():
                raise StorageError(f"Content package file is missing: {relative}")
            files.append((path, Path(relative).as_posix()))
        return files

    def _write_document(
        self, item_id: str, kind: ArtifactKind, filename: str, data: Any
    ) -> Path:
        self._ensure_supported_manifest(item_id)
        path = self._write_json(item_id, filename, data)
        self._refresh_manifest(
            item_id, changed=self._manifest_artifact_from_file(item_id, kind, filename)
        )
        return path

    def _manifest_artifact_from_file(
        self, item_id: str, kind: ArtifactKind, filename: str
    ) -> ManifestArtifact:
        path = self._directory(item_id) / filename
        return self._manifest_artifact(
            kind,
            filename,
            checksum=sha256_file(path),
            size=path.stat().st_size,
            mime=guess_mime(filename),
        )

    @staticmethod
    def _manifest_artifact(
        kind: ArtifactKind, filename: str, *, checksum: str, size: int, mime: str
    ) -> ManifestArtifact:
        return ManifestArtifact(
            kind=str(kind),
            path=filename,
            sha256=checksum,
            size=size,
            mime=mime,
        )

    def _refresh_manifest(
        self,
        item_id: str,
        *,
        changed: ManifestArtifact | None = None,
        removed_path: str | None = None,
    ) -> Path:
        existing = self.read_manifest(item_id)
        now = utc_ms()
        if existing is None:
            artifacts = self._scan_artifacts(item_id)
            if changed is not None:
                artifacts = [
                    artifact
                    for artifact in artifacts
                    if artifact.kind != changed.kind
                ]
                artifacts.append(changed)
            if removed_path is not None:
                artifacts = [
                    artifact for artifact in artifacts if artifact.path != removed_path
                ]
            created_at = now
            extra: dict[str, Any] = {}
        else:
            artifacts = list(existing.artifacts)
            if changed is not None:
                previous = next(
                    (artifact for artifact in artifacts if artifact.kind == changed.kind),
                    None,
                )
                if previous is not None:
                    artifacts.remove(previous)
                    changed = replace(changed, extra=dict(previous.extra))
                artifacts.append(changed)
            if removed_path is not None:
                artifacts = [
                    artifact for artifact in artifacts if artifact.path != removed_path
                ]
            created_at = existing.created_at
            extra = dict(existing.extra)
        artifacts.sort(
            key=lambda artifact: (
                _ARTIFACT_KIND_ORDER.get(
                    artifact.kind, len(_ARTIFACT_KIND_ORDER)
                ),
                artifact.path,
            )
        )
        return self.write_manifest(
            item_id,
            PackageManifest(
                schema_version=MANIFEST_SCHEMA_VERSION,
                item_id=item_id,
                created_at=created_at,
                updated_at=now,
                artifacts=artifacts,
                extra=extra,
            ),
        )

    def _scan_artifacts(self, item_id: str) -> list[ManifestArtifact]:
        directory = self._directory(item_id)
        artifacts: list[ManifestArtifact] = []
        for kind in ArtifactKind:
            path = self._find_artifact_file(directory, kind)
            if path is None:
                continue
            artifacts.append(
                ManifestArtifact(
                    kind=str(kind),
                    path=path.name,
                    sha256=sha256_file(path),
                    size=path.stat().st_size,
                    mime=guess_mime(path.name),
                )
            )
        return artifacts

    @staticmethod
    def _find_artifact_file(directory: Path, kind: ArtifactKind) -> Path | None:
        fixed = _FIXED_ARTIFACT_FILENAMES.get(str(kind))
        if fixed is not None:
            candidate = directory / fixed
            return candidate if candidate.is_file() else None
        prefix = _EXTENSION_ARTIFACT_PREFIXES[str(kind)]
        candidates = sorted(
            path for path in directory.glob(f"{prefix}.*") if path.is_file()
        )
        return candidates[0] if candidates else None

    def _validate_replacement(
        self, item_id: str, replaces: str | None, filename: str
    ) -> None:
        if replaces is not None and replaces != filename:
            self.artifact_path(item_id, replaces)

    def _remove_replaced(
        self, item_id: str, replaces: str | None, filename: str
    ) -> None:
        if replaces is not None and replaces != filename:
            self.artifact_path(item_id, replaces).unlink(missing_ok=True)

    def _read_document(self, item_id: str, filename: str) -> dict[str, Any] | None:
        data = self._read_json(item_id, filename)
        if data is None:
            return None
        if not isinstance(data, dict):
            raise StorageError(f"Invalid content package {filename}: expected an object")
        return data

    def _read_json(self, item_id: str, filename: str) -> Any | None:
        path = self._directory(item_id) / filename
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read content package {filename}: {exc}") from exc

    def _write_json(self, item_id: str, filename: str, data: Any) -> Path:
        path = self._directory(item_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            temporary.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            temporary.chmod(0o600)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def _install_temp(
        self, item_id: str, temp_path: Path, filename: str
    ) -> tuple[Path, str, int]:
        destination = self._directory(item_id) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        checksum = sha256_file(temp_path)
        size = temp_path.stat().st_size
        os.replace(temp_path, destination)
        destination.chmod(0o600)
        return destination, checksum, size

    def _copy_in(self, item_id: str, source: Path, filename: str) -> tuple[Path, str, int]:
        destination = self._directory(item_id) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{secrets.token_hex(4)}.tmp")
        checksum = hashlib.sha256()
        size = 0
        try:
            with source.open("rb") as reader, temporary.open("wb") as writer:
                while chunk := reader.read(CHUNK_SIZE):
                    checksum.update(chunk)
                    size += len(chunk)
                    writer.write(chunk)
            temporary.chmod(0o600)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination, checksum.hexdigest(), size

    def artifact_path(self, item_id: str, relative: str) -> Path:
        base = self._directory(item_id).resolve()
        candidate = (base / relative).resolve()
        if not candidate.is_relative_to(base):
            raise FileNotFoundError(relative)
        return candidate

    def remove(self, item_id: str) -> None:
        directory = self._directory(item_id)
        if directory.exists():
            shutil.rmtree(directory)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def guess_mime(filename: str) -> str:
    known = {
        ".m4a": "audio/mp4",
        ".epub": "application/epub+zip",
        ".json": "application/json",
    }.get(Path(filename).suffix.lower())
    if known is not None:
        return known
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"
