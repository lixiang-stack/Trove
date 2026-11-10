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

from trove.config import Config
from trove.errors import NotFoundError, ValidationError
from trove.ports import AudioExtractor, BookExtractor

AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".aiff"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
EPUB_SUFFIXES = {".epub"}
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
ALLOWED_CONTENT_TYPES = {
    "audio": ("audio/",),
    "video": ("video/",),
    "epub": ("application/epub+zip", "application/zip"),
}


@dataclass(slots=True)
class UploadRecord:
    upload_id: str
    filename: str
    path: str
    sha256: str
    size: int
    kind: str


class UploadStore:
    def __init__(
        self,
        config: Config,
        book_extractor: BookExtractor,
        audio_extractor: AudioExtractor,
    ) -> None:
        self.config = config
        self.book_extractor = book_extractor
        self.audio_extractor = audio_extractor

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
        suffix_kind = kind_for_suffix(suffix)
        if suffix_kind is None:
            raise ValidationError("Unsupported file type", details={"code": "upload.invalid_type"})
        if kind and kind != suffix_kind:
            raise ValidationError(
                "File type does not match the declared type",
                details={"code": "upload.invalid_type"},
            )
        detected_kind = suffix_kind
        check_content_type(detected_kind, content_type)
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
                            f"File exceeds the size limit ({limit // (1024 * 1024)} MB)",
                            details={"code": "upload.too_large"},
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            if size == 0:
                raise ValidationError("File is empty", details={"code": "upload.empty"})
            destination.chmod(0o600)
            if detected_kind == "epub":
                self.book_extractor.validate(destination)
            else:
                self.audio_extractor.probe(destination, kind=detected_kind)
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
            raise NotFoundError("Upload not found")
        path = self.config.uploads_dir / upload_id / "upload.json"
        if not path.exists():
            raise NotFoundError("Upload not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            record = UploadRecord(**data)
        except (OSError, json.JSONDecodeError, TypeError):
            raise NotFoundError("Upload not found") from None
        uploaded = Path(record.path).resolve()
        if not uploaded.is_relative_to(self.config.uploads_dir.resolve()):
            raise NotFoundError("Upload not found")
        if not uploaded.is_file():
            raise NotFoundError("Uploaded file has been cleaned up")
        record.path = str(uploaded)
        return record

    def cleanup(self, upload_id: str) -> None:
        shutil.rmtree(self.config.uploads_dir / upload_id, ignore_errors=True)

    def discard_for_path(self, path: str | Path | None) -> bool:
        if path is None:
            return False
        candidate = Path(path).resolve()
        root = self.config.uploads_dir.resolve()
        if not candidate.is_relative_to(root) or candidate == root:
            return False
        directory = candidate.parent
        if directory.parent != root:
            return False
        shutil.rmtree(directory, ignore_errors=True)
        return True


def check_content_type(kind: str, content_type: str | None) -> None:
    if not content_type or content_type == "application/octet-stream":
        return
    normalized = content_type.split(";", 1)[0].strip().lower()
    allowed = ALLOWED_CONTENT_TYPES[kind]
    if not any(normalized == value or normalized.startswith(value) for value in allowed):
        raise ValidationError("Unsupported file MIME type", details={"code": "upload.invalid_type"})


def kind_for_suffix(suffix: str) -> str | None:
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
