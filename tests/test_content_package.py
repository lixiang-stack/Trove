from __future__ import annotations

import json
from pathlib import Path

import pytest

from trove.config import Config
from trove.content_package import (
    MANIFEST_SCHEMA_VERSION,
    AiDocument,
    ArtifactKind,
    BookChapterDocument,
    BookCoverDocument,
    BookDocument,
    ContentPackage,
    FeedSourceDocument,
    ManifestArtifact,
    PackageManifest,
    SourceDocument,
    TranscriptDocument,
    TranscriptSegment,
    sha256_file,
)
from trove.domain.items import Platform, SourceType
from trove.errors import PackageVersionError, StorageError

ITEM_ID = "item-1"


@pytest.fixture
def package(tmp_path: Path) -> ContentPackage:
    return ContentPackage(Config(home=tmp_path))


def source_document() -> SourceDocument:
    return SourceDocument(
        id=ITEM_ID,
        source_key="https://example.com/watch?v=1",
        source_type=SourceType.VIDEO_URL,
        platform=Platform.YOUTUBE,
        title="Example",
        source_url_raw="https://example.com/watch?v=1",
        source_url_canonical="https://example.com/watch?v=1",
        author="Author",
        published_at="2026-11-01",
        fetched_at=1762000000000,
        language="en",
        duration_sec=12.5,
        uploaded=True,
        feed=FeedSourceDocument(
            url="https://example.com/feed.xml",
            episode_guid="ep-1",
            enclosure_url="https://example.com/ep.mp3",
            enclosure_type="audio/mpeg",
            enclosure_size=1234,
            extra={"future_feed": "kept"},
        ),
        extra={"future_field": {"nested": [1, 2]}},
    )


def transcript_document() -> TranscriptDocument:
    return TranscriptDocument(
        language="en",
        model="whisper",
        segments=[
            TranscriptSegment(
                seq=0,
                start_ms=0,
                end_ms=1000,
                text="Hello",
                extra={"confidence": 0.9},
            )
        ],
        extra={"source_version": 1},
    )


def book_document() -> BookDocument:
    return BookDocument(
        title="Book",
        author="Book Author",
        language="en",
        cover=BookCoverDocument(
            extension=".jpg",
            mime="image/jpeg",
            extra={"future_cover": True},
        ),
        chapters=[
            BookChapterDocument(
                chapter_index=0,
                title="One",
                html="<p>Hello</p>",
                text="Hello",
                paragraphs=["Hello"],
                extra={"anchor": "chapter-1"},
            )
        ],
        extra={"book_version": 2},
    )


def ai_document() -> AiDocument:
    return AiDocument(
        summary="A summary",
        tags=["tag"],
        model="deepseek-flash",
        prompt_version="v1",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.001,
        generated_at=1762000000000,
        extra={"future": True},
    )


def test_source_round_trip(package: ContentPackage) -> None:
    document = source_document()
    package.write_source(ITEM_ID, document)

    assert package.read_source(ITEM_ID) == document


def test_transcript_round_trip(package: ContentPackage) -> None:
    document = transcript_document()
    package.write_transcript(ITEM_ID, document)

    assert package.read_transcript(ITEM_ID) == document


def test_book_round_trip(package: ContentPackage) -> None:
    document = book_document()
    package.write_book(ITEM_ID, document)

    assert package.read_book(ITEM_ID) == document


def test_ai_round_trip(package: ContentPackage) -> None:
    document = ai_document()
    package.write_ai(ITEM_ID, document)

    assert package.read_ai(ITEM_ID) == document


@pytest.mark.parametrize(
    ("filename", "reader", "writer", "document"),
    [
        ("source.json", "read_source", "write_source", source_document()),
        ("transcript.json", "read_transcript", "write_transcript", transcript_document()),
        ("book.json", "read_book", "write_book", book_document()),
        ("ai.json", "read_ai", "write_ai", ai_document()),
    ],
)
def test_unknown_fields_survive_read_modify_write(
    package: ContentPackage,
    filename: str,
    reader: str,
    writer: str,
    document: object,
) -> None:
    getattr(package, writer)(ITEM_ID, document)
    path = package.artifact_path(ITEM_ID, filename)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["future_top_level"] = {"kept": True}
    path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = getattr(package, reader)(ITEM_ID)
    getattr(package, writer)(ITEM_ID, loaded)

    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["future_top_level"] == {"kept": True}


def test_missing_documents_return_none(package: ContentPackage) -> None:
    assert package.read_source(ITEM_ID) is None
    assert package.read_transcript(ITEM_ID) is None
    assert package.read_book(ITEM_ID) is None
    assert package.read_ai(ITEM_ID) is None


def test_corrupt_json_raises_storage_error(package: ContentPackage) -> None:
    path = package.artifact_path(ITEM_ID, "transcript.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(StorageError):
        package.read_transcript(ITEM_ID)


def _write_raw(package: ContentPackage, filename: str, payload: object) -> None:
    path = package.artifact_path(ITEM_ID, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_non_object_document_raises_storage_error(package: ContentPackage) -> None:
    _write_raw(package, "book.json", [])

    with pytest.raises(StorageError):
        package.read_book(ITEM_ID)


def test_invalid_enum_raises_storage_error(package: ContentPackage) -> None:
    _write_raw(
        package,
        "source.json",
        {
            "id": ITEM_ID,
            "source_key": "key",
            "source_type": "unknown",
            "platform": "local",
            "title": "Title",
        },
    )

    with pytest.raises(StorageError):
        package.read_source(ITEM_ID)


def test_missing_required_field_raises_storage_error(package: ContentPackage) -> None:
    _write_raw(
        package,
        "source.json",
        {
            "id": ITEM_ID,
            "source_key": "key",
            "source_type": "local_audio",
            "platform": "local",
        },
    )

    with pytest.raises(StorageError):
        package.read_source(ITEM_ID)


def test_install_artifact_moves_and_records(package: ContentPackage, tmp_path: Path) -> None:
    temp = tmp_path / "temp.m4a"
    temp.write_bytes(b"audio")

    installed = package.install_artifact(
        ITEM_ID, ArtifactKind.AUDIO, temp, extension=".m4a", mime="audio/mp4"
    )

    assert not temp.exists()
    assert installed.relative_path == "audio.m4a"
    assert installed.path.read_bytes() == b"audio"
    assert installed.sha256 == sha256_file(installed.path)
    assert installed.size == 5
    assert installed.mime == "audio/mp4"


def test_copy_artifact_keeps_the_source(package: ContentPackage, tmp_path: Path) -> None:
    source = tmp_path / "book.epub"
    source.write_bytes(b"book")

    installed = package.copy_artifact(ITEM_ID, ArtifactKind.BOOK, source)

    assert source.exists()
    assert installed.relative_path == "book.epub"
    assert installed.path.read_bytes() == b"book"


def test_install_artifact_replaces_the_previous_file(
    package: ContentPackage, tmp_path: Path
) -> None:
    first = tmp_path / "first.m4a"
    first.write_bytes(b"first")
    previous = package.install_artifact(
        ITEM_ID, ArtifactKind.AUDIO, first, extension=".m4a"
    )
    second = tmp_path / "second.mp3"
    second.write_bytes(b"second")

    installed = package.install_artifact(
        ITEM_ID,
        ArtifactKind.AUDIO,
        second,
        extension=".mp3",
        replaces=previous.relative_path,
    )

    assert installed.relative_path == "audio.mp3"
    assert not package.artifact_path(ITEM_ID, "audio.m4a").exists()
    assert package.artifact_path(ITEM_ID, "audio.mp3").read_bytes() == b"second"


def test_install_artifact_rejects_traversal_in_replaces(
    package: ContentPackage, tmp_path: Path
) -> None:
    temp = tmp_path / "temp.m4a"
    temp.write_bytes(b"audio")

    with pytest.raises(FileNotFoundError):
        package.install_artifact(
            ITEM_ID,
            ArtifactKind.AUDIO,
            temp,
            extension=".m4a",
            replaces="../../escape.m4a",
        )

    assert temp.exists()


def test_remove_artifact_deletes_the_file(
    package: ContentPackage, tmp_path: Path
) -> None:
    temp = tmp_path / "temp.m4a"
    temp.write_bytes(b"audio")
    installed = package.install_artifact(
        ITEM_ID, ArtifactKind.AUDIO, temp, extension=".m4a"
    )

    package.remove_artifact(ITEM_ID, installed.relative_path)
    package.remove_artifact(ITEM_ID, installed.relative_path)

    assert not installed.path.exists()


def test_remove_artifact_rejects_traversal(package: ContentPackage) -> None:
    with pytest.raises(FileNotFoundError):
        package.remove_artifact(ITEM_ID, "../../escape.m4a")


def test_export_files_includes_source_and_artifacts(
    package: ContentPackage, tmp_path: Path
) -> None:
    package.write_source(ITEM_ID, source_document())
    temp = tmp_path / "temp.m4a"
    temp.write_bytes(b"audio")
    package.install_artifact(ITEM_ID, ArtifactKind.AUDIO, temp, extension=".m4a")

    files = package.export_files(ITEM_ID, ["audio.m4a"])

    assert [name for _, name in files] == ["source.json", "audio.m4a"]
    assert all(path.is_file() for path, _ in files)


def test_export_files_rejects_missing_files(package: ContentPackage) -> None:
    with pytest.raises(StorageError):
        package.export_files(ITEM_ID, [])

    package.write_source(ITEM_ID, source_document())
    with pytest.raises(StorageError):
        package.export_files(ITEM_ID, ["missing.m4a"])


def manifest_document() -> PackageManifest:
    return PackageManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        item_id=ITEM_ID,
        created_at=1762000000000,
        updated_at=1762000001000,
        artifacts=[
            ManifestArtifact(
                kind="audio",
                path="audio.m4a",
                sha256="a" * 64,
                size=123,
                mime="audio/mp4",
                extra={"future_artifact": True},
            )
        ],
        extra={"future_manifest": {"kept": True}},
    )


def test_manifest_round_trip_preserves_unknown_fields(package: ContentPackage) -> None:
    document = manifest_document()
    package.write_manifest(ITEM_ID, document)

    loaded = package.read_manifest(ITEM_ID)
    assert loaded == document

    package.write_manifest(ITEM_ID, loaded)
    raw = json.loads(
        package.artifact_path(ITEM_ID, "manifest.json").read_text(encoding="utf-8")
    )
    assert raw["future_manifest"] == {"kept": True}
    assert raw["artifacts"][0]["future_artifact"] is True


def test_write_source_creates_a_manifest(package: ContentPackage) -> None:
    package.write_source(ITEM_ID, source_document())

    manifest = package.read_manifest(ITEM_ID)
    assert manifest is not None
    assert manifest.schema_version == MANIFEST_SCHEMA_VERSION
    assert manifest.item_id == ITEM_ID
    assert manifest.artifacts == []
    assert manifest.created_at <= manifest.updated_at


def test_incompatible_manifest_version_raises_a_stable_error(
    package: ContentPackage,
) -> None:
    package.write_source(ITEM_ID, source_document())
    package.write_transcript(ITEM_ID, transcript_document())
    _write_raw(
        package,
        "manifest.json",
        {
            "schema_version": MANIFEST_SCHEMA_VERSION + 1,
            "item_id": ITEM_ID,
            "created_at": 1,
            "updated_at": 2,
            "artifacts": [],
        },
    )

    for reader in (
        package.read_source,
        package.read_transcript,
        package.read_book,
        package.read_ai,
    ):
        with pytest.raises(PackageVersionError) as excinfo:
            reader(ITEM_ID)
        assert excinfo.value.code == "storage.package_version"

    with pytest.raises(PackageVersionError):
        package.write_source(ITEM_ID, source_document())


def test_manifest_item_id_must_match_the_directory(package: ContentPackage) -> None:
    document = manifest_document()
    document.item_id = "another-item"
    package.write_manifest(ITEM_ID, document)

    with pytest.raises(StorageError):
        package.read_manifest(ITEM_ID)


def test_manifest_without_schema_version_is_a_storage_error(
    package: ContentPackage,
) -> None:
    _write_raw(
        package,
        "manifest.json",
        {
            "item_id": ITEM_ID,
            "created_at": 1,
            "updated_at": 2,
            "artifacts": [],
        },
    )

    with pytest.raises(StorageError) as excinfo:
        package.read_manifest(ITEM_ID)
    assert excinfo.value.code == "storage.error"


def test_legacy_package_without_manifest_stays_readable_and_is_backfilled(
    package: ContentPackage, tmp_path: Path
) -> None:
    package.write_source(ITEM_ID, source_document())
    transcript = transcript_document()
    package.write_transcript(ITEM_ID, transcript)
    audio = tmp_path / "audio.m4a"
    audio.write_bytes(b"audio")
    installed = package.install_artifact(
        ITEM_ID, ArtifactKind.AUDIO, audio, extension=".m4a", mime="audio/mp4"
    )
    package.artifact_path(ITEM_ID, "manifest.json").unlink()

    assert package.read_manifest(ITEM_ID) is None
    assert package.read_source(ITEM_ID) == source_document()
    assert package.read_transcript(ITEM_ID) == transcript

    package.write_source(ITEM_ID, source_document())

    manifest = package.read_manifest(ITEM_ID)
    assert manifest is not None
    artifacts = {artifact.kind: artifact for artifact in manifest.artifacts}
    assert set(artifacts) == {"audio", "transcript"}
    assert artifacts["audio"].sha256 == installed.sha256
    assert artifacts["audio"].size == installed.size
    assert artifacts["audio"].mime == installed.mime
    assert artifacts["transcript"].sha256 == sha256_file(
        package.artifact_path(ITEM_ID, "transcript.json")
    )


def test_document_writes_refresh_manifest(package: ContentPackage) -> None:
    package.write_source(ITEM_ID, source_document())
    transcript_path = package.write_transcript(ITEM_ID, transcript_document())
    book_path = package.write_book(ITEM_ID, book_document())
    ai_path = package.write_ai(ITEM_ID, ai_document())

    manifest = package.read_manifest(ITEM_ID)
    assert manifest is not None
    artifacts = {artifact.kind: artifact for artifact in manifest.artifacts}
    assert set(artifacts) == {"transcript", "book_json", "ai"}
    for kind, path in (
        ("transcript", transcript_path),
        ("book_json", book_path),
        ("ai", ai_path),
    ):
        artifact = artifacts[kind]
        assert artifact.path == path.name
        assert artifact.sha256 == sha256_file(path)
        assert artifact.size == path.stat().st_size
        assert artifact.mime == "application/json"

    previous = artifacts["transcript"]
    package.write_transcript(ITEM_ID, TranscriptDocument(segments=[], model="changed"))

    manifest = package.read_manifest(ITEM_ID)
    assert manifest is not None
    updated = next(
        artifact for artifact in manifest.artifacts if artifact.kind == "transcript"
    )
    assert updated.sha256 != previous.sha256
    assert updated.size == package.artifact_path(ITEM_ID, "transcript.json").stat().st_size


def test_artifact_install_replace_and_remove_refresh_manifest(
    package: ContentPackage, tmp_path: Path
) -> None:
    first = tmp_path / "first.m4a"
    first.write_bytes(b"first")
    installed = package.install_artifact(
        ITEM_ID, ArtifactKind.AUDIO, first, extension=".m4a", mime="audio/mp4"
    )

    manifest = package.read_manifest(ITEM_ID)
    assert manifest is not None
    assert [
        (artifact.kind, artifact.path, artifact.sha256, artifact.size, artifact.mime)
        for artifact in manifest.artifacts
    ] == [("audio", "audio.m4a", installed.sha256, 5, "audio/mp4")]

    second = tmp_path / "second.mp3"
    second.write_bytes(b"second")
    replacement = package.install_artifact(
        ITEM_ID,
        ArtifactKind.AUDIO,
        second,
        extension=".mp3",
        mime="audio/mpeg",
        replaces=installed.relative_path,
    )

    manifest = package.read_manifest(ITEM_ID)
    assert manifest is not None
    assert [
        (artifact.kind, artifact.path, artifact.sha256, artifact.size, artifact.mime)
        for artifact in manifest.artifacts
    ] == [("audio", "audio.mp3", replacement.sha256, 6, "audio/mpeg")]

    package.remove_artifact(ITEM_ID, replacement.relative_path)

    manifest = package.read_manifest(ITEM_ID)
    assert manifest is not None
    assert manifest.artifacts == []

    cover_jpg = tmp_path / "cover.jpg"
    cover_jpg.write_bytes(b"cover-jpg")
    installed_cover = package.install_artifact(
        ITEM_ID, ArtifactKind.COVER, cover_jpg, extension=".jpg", mime="image/jpeg"
    )
    cover_png = tmp_path / "cover.png"
    cover_png.write_bytes(b"cover-png")
    replacement_cover = package.install_artifact(
        ITEM_ID,
        ArtifactKind.COVER,
        cover_png,
        extension=".png",
        mime="image/png",
        replaces=installed_cover.relative_path,
    )

    manifest = package.read_manifest(ITEM_ID)
    assert manifest is not None
    assert [
        (artifact.kind, artifact.path, artifact.sha256, artifact.size, artifact.mime)
        for artifact in manifest.artifacts
    ] == [
        (
            "cover",
            "cover.png",
            replacement_cover.sha256,
            replacement_cover.size,
            "image/png",
        )
    ]
