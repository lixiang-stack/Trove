from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import select

from trove.config import Config
from trove.content_package import ContentPackage, sha256_file
from trove.db.models import Artifact, Item
from trove.domain.items import Platform, SourceType
from trove.domain.urls import (
    canonicalize_feed_url,
    canonicalize_video_url,
    podcast_source_key,
)
from trove.errors import NotFoundError, ValidationError
from trove.ports import BookExtractor, FeedClient
from trove.services.library import ItemBundle, LibraryService
from trove.services.processing import ProcessingService

AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".aiff"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
EPUB_SUFFIXES = {".epub"}
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(slots=True)
class UploadRecord:
    upload_id: str
    filename: str
    path: str
    sha256: str
    size: int
    kind: str


class UploadStore:
    def __init__(self, config: Config) -> None:
        self.config = config

    def save_stream(
        self,
        stream: BinaryIO,
        filename: str,
        *,
        kind: str | None = None,
        content_type: str | None = None,
    ) -> UploadRecord:
        filename = Path(filename or "upload").name
        suffix = Path(filename).suffix.lower()
        suffix_kind = _kind_for_suffix(suffix)
        if suffix_kind is None:
            raise ValidationError("不支持的文件类型", details={"code": "upload.invalid_type"})
        if kind and kind != suffix_kind:
            raise ValidationError("文件类型与声明不符", details={"code": "upload.invalid_type"})
        detected_kind = suffix_kind
        _check_content_type(detected_kind, content_type)
        limit = {
            "audio": self.config.max_audio_bytes,
            "video": self.config.max_video_bytes,
            "epub": self.config.max_epub_bytes,
        }[detected_kind]
        upload_id = str(uuid.uuid4())
        directory = self.config.uploads_dir / upload_id
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        safe_name = SAFE_FILENAME_RE.sub("_", filename) or f"upload{suffix}"
        destination = directory / safe_name
        digest = hashlib.sha256()
        size = 0
        try:
            with destination.open("wb") as handle:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ValidationError(
                            f"文件超过大小限制（{limit // (1024 * 1024)} MB）",
                            details={"code": "upload.too_large"},
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if size == 0:
                raise ValidationError("文件为空", details={"code": "upload.empty"})
            destination.chmod(0o600)
            record = UploadRecord(
                upload_id=upload_id,
                filename=filename,
                path=str(destination),
                sha256=digest.hexdigest(),
                size=size,
                kind=detected_kind,
            )
            (directory / "upload.json").write_text(
                json.dumps(asdict(record), ensure_ascii=False), encoding="utf-8"
            )
            return record
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def load(self, upload_id: str) -> UploadRecord:
        if not re.fullmatch(r"[0-9a-f-]{36}", upload_id or ""):
            raise NotFoundError("上传不存在")
        path = self.config.uploads_dir / upload_id / "upload.json"
        if not path.exists():
            raise NotFoundError("上传不存在")
        data = json.loads(path.read_text(encoding="utf-8"))
        record = UploadRecord(**data)
        if not Path(record.path).exists():
            raise NotFoundError("上传文件已被清理")
        return record

    def cleanup(self, upload_id: str) -> None:
        shutil.rmtree(self.config.uploads_dir / upload_id, ignore_errors=True)


class IntakeService:
    def __init__(
        self,
        config: Config,
        package: ContentPackage,
        library: LibraryService,
        processing: ProcessingService,
        feed_client: FeedClient,
        book_extractor: BookExtractor,
        uploads: UploadStore,
    ) -> None:
        self.config = config
        self.package = package
        self.library = library
        self.processing = processing
        self.feed_client = feed_client
        self.book_extractor = book_extractor
        self.uploads = uploads

    # ------------------------------------------------------------------
    # Video URLs
    # ------------------------------------------------------------------
    def add_video_url(self, raw_url: str) -> tuple[ItemBundle, bool]:
        canonical = canonicalize_video_url(raw_url)
        bundle, deduplicated = self.library.create_item(
            source_key=canonical.source_key,
            source_type=SourceType.VIDEO_URL,
            platform=canonical.platform,
            title=canonical.canonical,
            source_url_raw=canonical.raw,
            source_url_canonical=canonical.canonical,
        )
        if not deduplicated:
            self.processing.create_run(bundle.item.id)
            return self.library.get(bundle.item.id), False
        return bundle, True

    # ------------------------------------------------------------------
    # Local paths
    # ------------------------------------------------------------------
    def add_host_path(self, raw_path: str) -> tuple[ItemBundle, bool]:
        if not raw_path or not raw_path.strip():
            raise ValidationError("文件路径不能为空", details={"code": "path.empty"})
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise ValidationError("请输入绝对路径", details={"code": "path.relative"})
        try:
            path = path.resolve(strict=True)
        except (OSError, FileNotFoundError) as exc:
            raise ValidationError("文件不存在", details={"code": "path.not_found"}) from exc
        if not path.is_file():
            raise ValidationError("路径不是文件", details={"code": "path.not_file"})
        if not path.stat().st_mode & 0o444:
            raise ValidationError("文件不可读", details={"code": "path.not_readable"})
        kind = _kind_for_suffix(path.suffix.lower())
        if kind is None:
            raise ValidationError("不支持的文件类型", details={"code": "upload.invalid_type"})
        checksum = sha256_file(path)
        return self._add_local_file(
            kind=kind,
            source_path=path,
            checksum=checksum,
            title=path.stem,
            uploaded=False,
        )

    def add_upload(self, upload_id: str) -> tuple[ItemBundle, bool]:
        record = self.uploads.load(upload_id)
        path = Path(record.path)
        try:
            bundle = self._add_local_file(
                kind=record.kind,
                source_path=path,
                checksum=record.sha256,
                title=Path(record.filename).stem,
                uploaded=True,
                size=record.size,
            )
        except Exception:
            self.uploads.cleanup(upload_id)
            raise
        if bundle[1] or record.kind == "epub":
            # Duplicates need no source; EPUB is copied into the package during intake.
            self.uploads.cleanup(upload_id)
        return bundle

    def _add_local_file(
        self,
        *,
        kind: str,
        source_path: Path,
        checksum: str,
        title: str,
        uploaded: bool,
        size: int | None = None,
    ) -> tuple[ItemBundle, bool]:
        source_type = {
            "audio": SourceType.LOCAL_AUDIO,
            "video": SourceType.LOCAL_VIDEO,
            "epub": SourceType.EPUB,
        }[kind]
        if kind == "epub":
            self.book_extractor.validate(source_path)
        existing = self._find_by_source_key(checksum)
        if existing is not None:
            return existing, True
        if kind == "epub" and size is not None and size > self.config.max_epub_bytes:
            raise ValidationError("EPUB 超过大小限制", details={"code": "upload.too_large"})
        bundle, deduplicated = self.library.create_item(
            source_key=checksum,
            source_type=source_type,
            platform=Platform.LOCAL,
            title=title,
            source_path=str(source_path),
            extra_source={"uploaded": uploaded},
        )
        if deduplicated:
            return bundle, True
        if kind == "epub":
            self._copy_book(bundle.item.id, source_path, checksum)
        self.processing.create_run(bundle.item.id)
        return self.library.get(bundle.item.id), False

    def _copy_book(self, item_id: str, source: Path, checksum: str) -> None:
        destination, actual_checksum, size = self.package.copy_in(item_id, source, "book.epub")
        with self.library.sessions() as session:
            session.add(
                Artifact(
                    item_id=item_id,
                    kind="book",
                    path=destination.name,
                    sha256=actual_checksum or checksum,
                    size=size,
                    mime="application/epub+zip",
                )
            )
            session.commit()

    def _find_by_source_key(self, source_key: str) -> ItemBundle | None:
        with self.library.sessions() as session:
            item = session.execute(
                select(Item).where(Item.source_key == source_key)
            ).scalars().first()
            if item is None:
                return None
            from trove.services.library import item_bundle

            return item_bundle(session, item)

    # ------------------------------------------------------------------
    # Podcast
    # ------------------------------------------------------------------
    def preview_feed(self, feed_url: str):
        canonical = canonicalize_feed_url(feed_url)
        return self.feed_client.preview(canonical)

    def add_podcast_episode(
        self,
        feed_url: str,
        episode_guid: str | None = None,
        enclosure_url: str | None = None,
    ) -> tuple[ItemBundle, bool]:
        canonical_feed = canonicalize_feed_url(feed_url)
        preview = self.feed_client.preview(canonical_feed)
        episode = next(
            (
                entry
                for entry in preview.episodes
                if (episode_guid and entry.guid == episode_guid)
                or (
                    not episode_guid
                    and enclosure_url
                    and entry.enclosure_url == enclosure_url
                )
            ),
            None,
        )
        if episode is None:
            raise ValidationError(
                "feed 中找不到该单集", details={"code": "feed.episode_not_found"}
            )
        source_key = podcast_source_key(canonical_feed, episode.guid, episode.enclosure_url)
        bundle, deduplicated = self.library.create_item(
            source_key=source_key,
            source_type=SourceType.PODCAST_EPISODE,
            platform=Platform.PODCAST,
            title=episode.title,
            source_url_raw=canonical_feed,
            source_url_canonical=canonical_feed,
            author=episode.author or preview.author,
            published_at=episode.published_at,
            duration_sec=episode.duration_sec,
            extra_source={
                "feed": {
                    "url": canonical_feed,
                    "episode_guid": episode.guid,
                    "enclosure_url": episode.enclosure_url,
                    "enclosure_type": episode.enclosure_type,
                    "enclosure_size": episode.enclosure_size,
                }
            },
        )
        if deduplicated:
            return bundle, True
        self.processing.create_run(bundle.item.id)
        return self.library.get(bundle.item.id), False


ALLOWED_CONTENT_TYPES = {
    "audio": ("audio/",),
    "video": ("video/",),
    "epub": ("application/epub+zip", "application/zip"),
}


def _check_content_type(kind: str, content_type: str | None) -> None:
    if not content_type or content_type == "application/octet-stream":
        return
    normalized = content_type.split(";", 1)[0].strip().lower()
    allowed = ALLOWED_CONTENT_TYPES[kind]
    if not any(normalized == value or normalized.startswith(value) for value in allowed):
        raise ValidationError("文件 MIME 类型不受支持", details={"code": "upload.invalid_type"})


def _kind_for_suffix(suffix: str) -> str | None:
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in EPUB_SUFFIXES:
        return "epub"
    mime, _ = mimetypes.guess_type(f"file{suffix}")
    if mime:
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("video/"):
            return "video"
    return None
