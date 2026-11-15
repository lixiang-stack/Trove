from __future__ import annotations

import hashlib
import shutil

from sqlalchemy import select

from trove.content_package import sha256_file
from trove.db.models import Artifact

from .conftest import seed_item
from .fakes import FIXTURES

KINDS = {
    "audio": ("audio.m4a", "audio/mp4"),
    "transcript": ("transcript.json", "application/json"),
    "book": ("book.epub", "application/epub+zip"),
    "book_json": ("book.json", "application/json"),
    "ai": ("ai.json", "application/json"),
    "cover": ("cover.png", "image/png"),
}
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000000020001e221bc330000000049454e44ae426082"
)


def _install(host, item_id: str, kind: str) -> Artifact:
    filename, mime = KINDS[kind]
    destination = host.config.library_dir / item_id / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if kind == "cover":
        destination.write_bytes(PNG)
    elif kind in {"book_json", "ai"}:
        destination.write_bytes(FIXTURES.joinpath("transcript.json").read_bytes())
    else:
        source = FIXTURES / {
            "audio": "short.m4a",
            "book": "aesop.epub",
        }.get(kind, filename)
        shutil.copyfile(source, destination)
    with host.runtime.sessions() as session:
        artifact = session.execute(
            select(Artifact).where(Artifact.item_id == item_id, Artifact.kind == kind)
        ).scalars().first()
        if artifact is None:
            artifact = Artifact(
                item_id=item_id,
                kind=kind,
                path=filename,
                sha256=sha256_file(destination),
                size=destination.stat().st_size,
                mime=mime,
            )
            session.add(artifact)
        else:
            artifact.path = filename
            artifact.sha256 = sha256_file(destination)
            artifact.size = destination.stat().st_size
            artifact.mime = mime
        session.commit()
        session.refresh(artifact)
        return artifact


def test_all_six_kinds_download_with_media_headers(host):
    bundle = seed_item(host, title="Files", with_audio=True)
    for kind in KINDS:
        _install(host, bundle.item.id, kind)
    host.login()
    for kind, (filename, mime) in KINDS.items():
        response = host.client.get(f"/api/items/{bundle.item.id}/files/{kind}")
        assert response.status_code == 200, (kind, response.text)
        assert response.headers["content-type"].startswith(mime)
        assert response.headers["accept-ranges"] == "bytes"
        assert response.headers["cache-control"] == "private"
        assert response.headers["x-content-type-options"] == "nosniff"
        expected = host.config.library_dir / bundle.item.id / filename
        assert response.headers["etag"] == f'"{sha256_file(expected)}"'
        assert hashlib.sha256(response.content).hexdigest() == sha256_file(expected)


def test_missing_and_unknown_artifacts_are_stable_404s(host):
    bundle = seed_item(host, title="Files", with_audio=False)
    host.login()
    missing = host.client.get(f"/api/items/{bundle.item.id}/files/audio")
    assert missing.status_code == 404
    assert missing.json()["code"] == "file.artifact_missing"

    unknown = host.client.get(f"/api/items/{bundle.item.id}/files/secrets")
    assert unknown.status_code == 404

    no_item = host.client.get("/api/items/missing/files/audio")
    assert no_item.status_code == 404


def test_range_and_if_range_resume(host):
    bundle = seed_item(host, title="Range", with_audio=True)
    host.login()
    artifact = _install(host, bundle.item.id, "audio")
    etag = f'"{artifact.sha256}"'

    partial = host.client.get(
        f"/api/items/{bundle.item.id}/files/audio",
        headers={"range": "bytes=0-9"},
    )
    assert partial.status_code == 206
    assert partial.headers["content-range"] == f"bytes 0-9/{artifact.size}"
    assert len(partial.content) == 10

    resumed = host.client.get(
        f"/api/items/{bundle.item.id}/files/audio",
        headers={"range": "bytes=10-19", "if-range": etag},
    )
    assert resumed.status_code == 206
    assert resumed.content == (
        host.config.library_dir / bundle.item.id / "audio.m4a"
    ).read_bytes()[10:20]

    full = host.client.get(
        f"/api/items/{bundle.item.id}/files/audio",
        headers={"range": "bytes=10-19", "if-range": '"stale-etag"'},
    )
    assert full.status_code == 200
    assert len(full.content) == artifact.size


def test_artifact_path_traversal_is_refused(host):
    bundle = seed_item(host, title="Traversal", with_audio=False)
    outside = host.config.home / "outside-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    with host.runtime.sessions() as session:
        session.add(
            Artifact(
                item_id=bundle.item.id,
                kind="audio",
                path="../../outside-secret.txt",
                sha256="x",
                size=6,
                mime="audio/mp4",
            )
        )
        session.commit()
    host.login()
    response = host.client.get(f"/api/items/{bundle.item.id}/files/audio")
    assert response.status_code == 404
    assert response.json()["code"] == "file.artifact_missing"


def test_files_require_authentication(api_host):
    bundle = seed_item(api_host, title="Auth", with_audio=True)
    response = api_host.client.get(f"/api/items/{bundle.item.id}/files/audio")
    assert response.status_code == 401


def test_bearer_can_download_files(api_host):
    bundle = seed_item(api_host, title="Bearer", with_audio=True)
    token = api_host.client.post(
        "/api/auth/device-token", json={"password": "test-password", "name": "Pixel"}
    ).json()["token"]
    api_host.client.cookies.clear()
    response = api_host.client.get(
        f"/api/items/{bundle.item.id}/files/audio",
        headers={"authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.headers["etag"].startswith('"')


def test_deleted_item_files_are_not_available(host):
    bundle = seed_item(host, title="Deleted files", with_audio=True)
    host.login()
    host.client.delete(f"/api/items/{bundle.item.id}")
    response = host.client.get(f"/api/items/{bundle.item.id}/files/audio")
    assert response.status_code == 404
