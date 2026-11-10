from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import secrets
import shutil
from pathlib import Path
from typing import Any

from trove.config import Config
from trove.errors import TroveError

CHUNK_SIZE = 1024 * 1024


class ContentPackage:
    def __init__(self, config: Config) -> None:
        self.config = config

    def directory(self, item_id: str) -> Path:
        return self.config.library_dir / item_id

    def ensure(self, item_id: str) -> Path:
        directory = self.directory(item_id)
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        return directory

    def source_path(self, item_id: str) -> Path:
        return self.directory(item_id) / "source.json"

    def read_json(self, item_id: str, filename: str) -> Any | None:
        path = self.directory(item_id) / filename
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise TroveError(f"Could not read content package {filename}: {exc}") from exc

    def read_source(self, item_id: str) -> dict[str, Any]:
        data = self.read_json(item_id, "source.json")
        return data if isinstance(data, dict) else {}

    def write_source(self, item_id: str, data: dict[str, Any]) -> None:
        self.write_json(item_id, "source.json", data)

    def write_json(self, item_id: str, filename: str, data: Any) -> Path:
        path = self.directory(item_id) / filename
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

    def install_temp(self, item_id: str, temp_path: Path, filename: str) -> tuple[Path, str, int]:
        destination = self.directory(item_id) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        checksum = sha256_file(temp_path)
        size = temp_path.stat().st_size
        os.replace(temp_path, destination)
        destination.chmod(0o600)
        return destination, checksum, size

    def copy_in(self, item_id: str, source: Path, filename: str) -> tuple[Path, str, int]:
        destination = self.directory(item_id) / filename
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
        base = self.directory(item_id).resolve()
        candidate = (base / relative).resolve()
        if not candidate.is_relative_to(base):
            raise FileNotFoundError(relative)
        return candidate

    def remove(self, item_id: str) -> None:
        directory = self.directory(item_id)
        if directory.exists():
            shutil.rmtree(directory)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def guess_mime(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    if mime:
        return mime
    suffixes = Path(filename).suffix.lower()
    return {
        ".m4a": "audio/mp4",
        ".epub": "application/epub+zip",
        ".json": "application/json",
    }.get(suffixes, "application/octet-stream")
