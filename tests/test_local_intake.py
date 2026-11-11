from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from .fakes import FIXTURES


def _rewrite_epub(
    source: Path,
    destination: Path,
    *,
    opf_replace: tuple[str, str] | None = None,
    extra: dict[str, bytes] | None = None,
) -> None:
    with zipfile.ZipFile(source) as reader, zipfile.ZipFile(destination, "w") as writer:
        for info in reader.infolist():
            data = reader.read(info.filename)
            if info.filename == "OEBPS/content.opf" and opf_replace:
                data = data.replace(opf_replace[0].encode(), opf_replace[1].encode())
            writer.writestr(info, data)
        for name, data in (extra or {}).items():
            writer.writestr(name, data)


@pytest.mark.ffmpeg
def test_upload_audio_creates_item_and_cleans_temp(host):
    host.login()
    record = host.client.post(
        "/api/uploads",
        files={"file": ("sample.wav", (FIXTURES / "short.wav").read_bytes(), "audio/wav")},
    )
    assert record.status_code == 200, record.text
    upload_id = record.json()["upload_id"]
    response = host.client.post("/api/items", json={"kind": "upload", "upload_id": upload_id})
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["processing_state"] == "completed"
    item_dir = host.config.library_dir / item_id
    assert (item_dir / "audio.wav").is_file()
    assert (item_dir / "source.json").is_file()
    assert not (host.config.uploads_dir / upload_id).exists()


def test_upload_rejects_unknown_type_and_cleans_temp(host):
    host.login()
    response = host.client.post(
        "/api/uploads",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "upload.invalid_type"
    assert list(host.config.uploads_dir.iterdir()) == []


def test_upload_rejects_size_over_limit_and_cleans_temp(host):
    host.login()
    runtime = host.runtime
    runtime.config.max_audio_bytes = 1024
    response = host.client.post(
        "/api/uploads",
        files={"file": ("large.wav", b"x" * 4096, "audio/wav")},
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "upload.too_large"
    assert list(host.config.uploads_dir.iterdir()) == []


def test_upload_epub_is_copied_and_parsed(host):
    host.login()
    upload = host.client.post(
        "/api/uploads",
        files={
            "file": (
                "aesop.epub",
                (FIXTURES / "aesop.epub").read_bytes(),
                "application/epub+zip",
            )
        },
    )
    assert upload.status_code == 200, upload.text
    upload_id = upload.json()["upload_id"]
    response = host.client.post("/api/items", json={"kind": "upload", "upload_id": upload_id})
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["processing_state"] == "completed"
    assert payload["has_book"] is True
    item_dir = host.config.library_dir / item_id
    assert (item_dir / "book.epub").is_file()
    assert (item_dir / "book.json").is_file()
    assert not (host.config.uploads_dir / upload_id).exists()


@pytest.mark.ffmpeg
def test_host_path_audio_is_copied_not_moved(host):
    source = host.config.home / "user-audio.wav"
    shutil.copyfile(FIXTURES / "short.wav", source)
    before = source.read_bytes()
    host.login()
    response = host.client.post("/api/items", json={"kind": "path", "path": str(source)})
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    assert source.read_bytes() == before
    assert (host.config.library_dir / item_id / "audio.wav").is_file()


@pytest.mark.ffmpeg
def test_local_video_keeps_path_but_not_video_file(host):
    source = host.config.home / "user-video.mp4"
    shutil.copyfile(FIXTURES / "short.mp4", source)
    host.login()
    response = host.client.post("/api/items", json={"kind": "path", "path": str(source)})
    assert response.status_code == 201, response.text
    payload = response.json()["item"]
    assert payload["source_path"] == str(source)
    item_id = payload["id"]
    host.wait_for_item(item_id)
    item_dir = host.config.library_dir / item_id
    assert (item_dir / "audio.m4a").is_file()
    assert not list(item_dir.glob("*.mp4"))
    assert not list(item_dir.glob("*.webm"))
    assert source.exists()


def test_duplicate_local_file_is_deduplicated(host):
    source = host.config.home / "duplicate.wav"
    shutil.copyfile(FIXTURES / "short.wav", source)
    host.login()
    first = host.client.post("/api/items", json={"kind": "path", "path": str(source)})
    item_id = first.json()["item"]["id"]
    host.wait_for_item(item_id)
    second = host.client.post("/api/items", json={"kind": "path", "path": str(source)})
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["item"]["id"] == item_id


@pytest.mark.ffmpeg
def test_unsupported_audio_is_transcoded(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "path", "path": str(FIXTURES / "short.flac")}
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    assert (host.config.library_dir / item_id / "audio.m4a").is_file()


def test_epub_drm_and_fixed_layout_are_rejected(host, tmp_path):
    drm = tmp_path / "drm.epub"
    encryption = b"""<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#">
    <CipherData><CipherReference URI="OEBPS/chapter1.xhtml"/></CipherData>
  </EncryptedData>
</encryption>"""
    _rewrite_epub(FIXTURES / "aesop.epub", drm, extra={"META-INF/encryption.xml": encryption})
    fixed = tmp_path / "fixed.epub"
    _rewrite_epub(
        FIXTURES / "oedipus.epub",
        fixed,
        opf_replace=(
            "</metadata>",
            '<meta property="rendition:layout">pre-paginated</meta></metadata>',
        ),
    )
    host.login()
    response = host.client.post("/api/items", json={"kind": "path", "path": str(drm)})
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "epub.drm"
    response = host.client.post("/api/items", json={"kind": "path", "path": str(fixed)})
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "epub.fixed_layout"


def test_invalid_epub_is_rejected(host, tmp_path):
    invalid = tmp_path / "not-a-book.epub"
    invalid.write_bytes(b"not a zip")
    host.login()
    response = host.client.post("/api/items", json={"kind": "path", "path": str(invalid)})
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "epub.invalid"


def test_path_validation(host):
    host.login()
    response = host.client.post("/api/items", json={"kind": "path", "path": "relative.mp3"})
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "path.relative"
    response = host.client.post("/api/items", json={"kind": "path", "path": str(host.config.home)})
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "path.not_file"
    response = host.client.post(
        "/api/items", json={"kind": "path", "path": str(host.config.home / "missing.mp3")}
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "path.not_found"


def test_add_page_has_upload_progress_ui(host):
    host.login()
    page = host.client.get("/add")
    assert 'id="upload-form"' in page.text
    assert 'id="upload-progress"' in page.text
    script = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "trove"
        / "web"
        / "static"
        / "player.js"
    ).read_text()
    assert "XMLHttpRequest" in script


def test_failed_upload_validation_cleans_temp(host):
    host.login()
    upload = host.client.post(
        "/api/uploads",
        files={"file": ("broken.epub", b"not a zip", "application/epub+zip")},
    )
    assert upload.status_code == 200
    upload_id = upload.json()["upload_id"]
    response = host.client.post("/api/items", json={"kind": "upload", "upload_id": upload_id})
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "epub.invalid"
    assert not (host.config.uploads_dir / upload_id).exists()


def test_upload_rejects_wrong_mime_type(host):
    host.login()
    response = host.client.post(
        "/api/uploads",
        files={"file": ("audio.wav", b"not really audio", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["details"]["code"] == "upload.invalid_type"
    assert list(host.config.uploads_dir.iterdir()) == []
