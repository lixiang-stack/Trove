from __future__ import annotations

import io
import zipfile

from trove.clock import utc_ms
from trove.content_package import (
    AiDocument,
    TranscriptDocument,
    TranscriptSegment,
    sha256_file,
)

from .conftest import seed_item
from .fakes import FIXTURES


def _add_book(host) -> str:
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "path", "path": str(FIXTURES / "aesop.epub")}
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    return item_id


def _seed_video(host):
    bundle = seed_item(
        host,
        title="Export video",
        source_type="video_url",
        platform="youtube",
        source_url_raw="https://www.youtube.com/watch?v=export",
        source_url_canonical="https://www.youtube.com/watch?v=export",
        summary="视频摘要",
        tags=["导出"],
        consumption_state="in_progress",
        position=12.0,
        duration=100.0,
    )
    item_id = bundle.item.id
    with host.runtime.sessions() as session:
        from trove.db.models import Artifact

        transcript = host.runtime.package.write_transcript(
            item_id,
            TranscriptDocument(
                language="zh",
                segments=[
                    TranscriptSegment(seq=0, start_ms=0, end_ms=1000, text="导出测试")
                ],
            ),
        )
        session.add(
            Artifact(
                item_id=item_id,
                kind="transcript",
                path=transcript.name,
                sha256=sha256_file(transcript),
                size=transcript.stat().st_size,
                mime="application/json",
            )
        )
        ai = host.runtime.package.write_ai(
            item_id,
            AiDocument(
                summary="视频摘要",
                tags=["导出"],
                model="fake",
                prompt_version="v1",
                input_tokens=1,
                output_tokens=1,
                cost_usd=0.0,
                generated_at=utc_ms(),
            ),
        )
        session.add(
            Artifact(
                item_id=item_id,
                kind="ai",
                path=ai.name,
                sha256=sha256_file(ai),
                size=ai.stat().st_size,
                mime="application/json",
            )
        )
        session.commit()
    return item_id


def _zip(response) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_export_all_contains_content_packages_and_markdown_index(host):
    video_id = _seed_video(host)
    book_id = _add_book(host)
    host.login()
    response = host.client.get("/api/export")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    archive = _zip(response)
    names = set(archive.namelist())
    assert "index.md" in names
    for name in (
        f"items/{video_id}/source.json",
        f"items/{video_id}/audio.m4a",
        f"items/{video_id}/transcript.json",
        f"items/{video_id}/ai.json",
        f"items/{book_id}/source.json",
        f"items/{book_id}/book.epub",
        f"items/{book_id}/book.json",
        f"items/{book_id}/ai.json",
    ):
        assert name in names
    assert not any(name.endswith((".mp4", ".webm", ".mov", ".mkv")) for name in names)

    index = archive.read("index.md").decode("utf-8")
    assert "Export video" in index
    assert "Aesop Fables" in index
    assert "视频摘要" in index
    assert "导出" in index
    assert "transcript.json" in index
    assert "https://www.youtube.com/watch?v=export" in index
    assert "audio.m4a" in index


def test_export_subset_and_empty_selection(host):
    video_id = _seed_video(host)
    book_id = _add_book(host)
    host.login()
    subset = host.client.get("/api/export", params={"ids": book_id})
    assert subset.status_code == 200
    names = set(_zip(subset).namelist())
    assert f"items/{book_id}/source.json" in names
    assert not any(name.startswith(f"items/{video_id}/") for name in names)
    index = _zip(subset).read("index.md").decode("utf-8")
    assert "Aesop Fables" in index
    assert "Export video" not in index

    empty = host.client.get("/api/export?ids=")
    assert empty.status_code == 200
    empty_names = set(_zip(empty).namelist())
    assert empty_names == {"index.md"}

    form_style = host.client.get("/api/export", params=[("ids", ""), ("ids", video_id)])
    form_names = set(_zip(form_style).namelist())
    assert f"items/{video_id}/source.json" in form_names
    assert not any(name.startswith(f"items/{book_id}/") for name in form_names)


def test_export_unknown_item_returns_stable_error_and_cleans_up(host):
    host.login()
    response = host.client.get("/api/export", params={"ids": "missing"})
    assert response.status_code == 404
    assert response.json()["details"]["code"] == "export.unknown_item"
    exports = host.config.cache_dir / "exports"
    assert not exports.exists() or list(exports.iterdir()) == []


def test_export_does_not_modify_the_library(host):
    video_id = _seed_video(host)
    item_dir = host.config.library_dir / video_id
    before = {
        path.name: (path.stat().st_size, path.read_bytes()) for path in item_dir.iterdir()
    }
    host.login()
    response = host.client.get("/api/export", params={"ids": video_id})
    assert response.status_code == 200
    after = {
        path.name: (path.stat().st_size, path.read_bytes()) for path in item_dir.iterdir()
    }
    assert after == before


def test_export_failure_cleans_up_temporary_zip(host):
    from sqlalchemy import text

    video_id = _seed_video(host)
    with host.runtime.sessions() as session:
        session.execute(
            text(
                "UPDATE artifacts SET path = '../outside.m4a' "
                "WHERE item_id = :item_id AND kind = 'audio'"
            ),
            {"item_id": video_id},
        )
        session.commit()
    host.login()
    response = host.client.get("/api/export", params={"ids": video_id})
    assert response.status_code == 500
    exports = host.config.cache_dir / "exports"
    assert not exports.exists() or list(exports.iterdir()) == []


def test_html_export_entries_download_a_zip(host):
    video_id = _seed_video(host)
    host.login()
    library = host.client.get("/library")
    assert 'href="/export"' not in library.text
    assert 'id="export-form"' in library.text
    assert "data-export-select-all" in library.text
    assert "data-export-submit disabled" in library.text
    assert 'name="ids" value=""' in library.text
    assert f'name="ids" value="{video_id}" form="export-form"' in library.text
    detail = host.client.get(f"/items/{video_id}")
    assert f'href="/export?ids={video_id}"' in detail.text
    response = host.client.get("/export", params={"ids": video_id})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"items/{video_id}/source.json" in _zip(response).namelist()
