from __future__ import annotations

from pathlib import Path

from trove.cli import main
from trove.config import Config
from trove.content_package import (
    MANIFEST_SCHEMA_VERSION,
    ContentPackage,
    ManifestArtifact,
    PackageManifest,
    SourceDocument,
    sha256_file,
)
from trove.domain.items import Platform, SourceType

ITEM_ID = "package-item"


def _write_package(tmp_path: Path) -> tuple[ContentPackage, Path, Path]:
    config = Config(home=tmp_path / "Trove")
    config.ensure_layout()
    package = ContentPackage(config)
    package.write_source(
        ITEM_ID,
        SourceDocument(
            id=ITEM_ID,
            source_key="https://example.com/watch?v=1",
            source_type=SourceType.VIDEO_URL,
            platform=Platform.YOUTUBE,
            title="Package item",
        ),
    )
    audio = config.library_dir / ITEM_ID / "audio.m4a"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"audio")
    package.write_manifest(
        ITEM_ID,
        PackageManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            item_id=ITEM_ID,
            created_at=1,
            updated_at=1,
            artifacts=[
                ManifestArtifact(
                    kind="audio",
                    path="audio.m4a",
                    sha256=sha256_file(audio),
                    size=audio.stat().st_size,
                    mime="audio/mp4",
                )
            ],
        ),
    )
    return package, audio, config.home


def test_package_verify_accepts_a_matching_manifest(
    tmp_path: Path, capsys
) -> None:
    _, _, home = _write_package(tmp_path)

    assert main(["--home", str(home), "package", "verify", ITEM_ID]) == 0
    assert "verified" in capsys.readouterr().out


def test_package_verify_reports_missing_and_corrupt_artifacts(
    tmp_path: Path, capsys
) -> None:
    package, audio, home = _write_package(tmp_path)

    audio.unlink()
    assert main(["--home", str(home), "package", "verify", ITEM_ID]) == 1
    assert "file is missing" in capsys.readouterr().err

    audio.write_bytes(b"other")
    assert main(["--home", str(home), "package", "verify", ITEM_ID]) == 1
    assert "sha256 mismatch" in capsys.readouterr().err

    audio.write_bytes(b"longer")
    assert main(["--home", str(home), "package", "verify", ITEM_ID]) == 1
    assert "size is 6" in capsys.readouterr().err

    package.artifact_path(ITEM_ID, "manifest.json").unlink()
    assert main(["--home", str(home), "package", "verify", ITEM_ID]) == 1
    assert "manifest is missing" in capsys.readouterr().err

    package.artifact_path(ITEM_ID, "source.json").unlink()
    assert main(["--home", str(home), "package", "verify", ITEM_ID]) == 1
    assert "source.json: file is missing" in capsys.readouterr().err

    assert main(["--home", str(home), "package", "verify", "missing-item"]) == 1
    assert "content package directory is missing" in capsys.readouterr().err
