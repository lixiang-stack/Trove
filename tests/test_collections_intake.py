from __future__ import annotations

import json
import shutil

from sqlalchemy import select

from trove.db.models import Run
from trove.ports import AudioResult, LinkProbeResult, VideoInfo

from .fakes import FIXTURES, video_collection

PLAYLIST = "https://www.youtube.com/playlist?list=PLtestcollection"
EPISODE_1 = "https://www.youtube.com/watch?v=episode0001"
EPISODE_2 = "https://www.youtube.com/watch?v=episode0002"
EPISODE_3 = "https://www.youtube.com/watch?v=episode0003"


def _seed_collection(host, *, title: str = "Fixture Collection") -> None:
    host.stack.video_inspector.collections[PLAYLIST] = video_collection(
        title,
        [
            ("Episode One", EPISODE_1, 120.0),
            ("Episode Two", EPISODE_2, 90.0),
            ("Episode Three", EPISODE_3, 60.0),
        ],
    )


def _stub_audio_extraction(monkeypatch, host) -> None:
    def extract(source, output_dir, *, force_transcode, context):
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "audio.m4a"
        shutil.copyfile(FIXTURES / "short.m4a", path)
        return AudioResult(
            path=path,
            duration_sec=2.0,
            mime="audio/mp4",
            extension=".m4a",
        )

    monkeypatch.setattr(host.stack.audio_extractor.real, "extract", extract)


def test_youtube_playlist_inspect_create_and_readd(api_host):
    _seed_collection(api_host)
    api_host.login()

    inspected = api_host.client.post(
        "/api/intake/inspect", json={"url": PLAYLIST}
    )
    assert inspected.status_code == 200, inspected.text
    preview = inspected.json()
    assert preview["kind"] == "collection"
    assert preview["episode_count"] == 3
    assert preview["total_duration_sec"] == 270.0
    assert [entry["title"] for entry in preview["episodes"]] == [
        "Episode One",
        "Episode Two",
        "Episode Three",
    ]

    created = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["added_count"] == 3
    assert payload["attached_count"] == 0
    assert payload["run_count"] == 3
    collection = payload["collection"]
    assert collection["episode_count"] == 3
    assert collection["status"]["queued"] == 3
    assert len(collection["items"]) == 3
    assert collection["items"][0]["collection_index"] == 1

    repeated = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    assert repeated.status_code == 201, repeated.text
    repeated_payload = repeated.json()
    assert repeated_payload["added_count"] == 0
    assert repeated_payload["attached_count"] == 3
    assert repeated_payload["run_count"] == 0

    # Add an episode upstream and append it.
    api_host.stack.video_inspector.collections[PLAYLIST] = video_collection(
        "Fixture Collection",
        [
            ("Episode One", EPISODE_1, 120.0),
            ("Episode Two", EPISODE_2, 90.0),
            ("Episode Three", EPISODE_3, 60.0),
            ("Episode Four", "https://www.youtube.com/watch?v=episode0004", 30.0),
        ],
    )
    appended = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    assert appended.status_code == 201, appended.text
    appended_payload = appended.json()
    assert appended_payload["added_count"] == 1
    assert appended_payload["attached_count"] == 3
    assert appended_payload["run_count"] == 1

    # Remove an episode upstream: local item is retained, with a warning.
    api_host.stack.video_inspector.collections[PLAYLIST] = video_collection(
        "Fixture Collection",
        [
            ("Episode One", EPISODE_1, 120.0),
            ("Episode Two", EPISODE_2, 90.0),
        ],
    )
    removed_preview = api_host.client.post(
        "/api/intake/inspect", json={"url": PLAYLIST}
    ).json()
    assert removed_preview["upstream_removed_count"] == 2
    assert any(
        warning["code"] == "collection.upstream_removed"
        for warning in removed_preview["warnings"]
    )
    retained = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    assert retained.status_code == 201, retained.text
    assert retained.json()["collection"]["episode_count"] == 4


def test_collection_episodes_share_tags_and_context(host, monkeypatch):
    _stub_audio_extraction(monkeypatch, host)
    _seed_collection(host)
    host.login()
    created = host.client.post("/api/collections", json={"url": PLAYLIST})
    assert created.status_code == 201, created.text
    item_ids = [item["id"] for item in created.json()["collection"]["items"]]
    for item_id in item_ids:
        host.wait_for_item(item_id)

    calls = host.stack.organizer.collection_calls
    assert len(calls) == 3
    assert {call[0] for call in calls} == {"Fixture Collection"}
    assert {call[1] for call in calls} == {1, 2, 3}
    bootstrap = [call for call in calls if not call[2]]
    reuse = [call for call in calls if call[2]]
    assert len(bootstrap) == 1
    assert len(reuse) == 2
    for call, existing in zip(
        calls, host.stack.organizer.existing_tags_calls, strict=True
    ):
        if call[2]:
            assert set(host.stack.organizer.tags) <= set(existing)


def test_collection_reprocess_cli_resets_ai_tags(host, monkeypatch, capsys):
    _stub_audio_extraction(monkeypatch, host)
    _seed_collection(host)
    host.login()
    created = host.client.post("/api/collections", json={"url": PLAYLIST})
    assert created.status_code == 201, created.text
    collection_id = created.json()["collection"]["id"]
    item_ids = [item["id"] for item in created.json()["collection"]["items"]]
    for item_id in item_ids:
        host.wait_for_item(item_id)
    assert host.item(item_ids[0])["tags"]

    added = host.client.post(
        f"/api/items/{item_ids[0]}/tags", json={"tag": "我自己的标签"}
    )
    assert added.status_code == 200, added.text
    from trove.cli import main

    home = str(host.config.home)
    assert (
        main(
            [
                "--home",
                home,
                "collection",
                "reprocess",
                collection_id,
                "--from-stage",
                "downloading",
                "--reset-ai-tags",
            ]
        )
        == 2
    )
    assert len(host.item(item_ids[0])["tags"]) > 1

    host.worker.stop()
    assert (
        main(
            [
                "--home",
                home,
                "collection",
                "reprocess",
                collection_id,
                "--reset-ai-tags",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Deleted" in output and "queued 3 organizing runs" in output

    assert host.item(item_ids[0])["tags"] == ["我自己的标签"]
    for item_id in item_ids[1:]:
        assert host.item(item_id)["tags"] == []
    for item_id in item_ids:
        assert host.item(item_id)["run"]["state"] == "queued"
        with host.runtime.sessions() as session:
            run = session.execute(
                select(Run).where(Run.item_id == item_id, Run.state == "queued")
            ).scalars().first()
        assert run is not None
        assert run.force is True


def test_existing_episode_is_attached_and_other_collection_conflicts(api_host):
    api_host.login()
    single = api_host.client.post(
        "/api/items", json={"kind": "url", "url": EPISODE_1}
    )
    assert single.status_code == 201, single.text
    item_id = single.json()["item"]["id"]

    _seed_collection(api_host)
    created = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["attached_count"] == 1
    assert payload["added_count"] == 2
    attached = api_host.client.get(f"/api/items/{item_id}").json()
    assert attached["collection_id"] is not None
    assert attached["collection_index"] == 1
    assert attached["collection_title"] == "Fixture Collection"

    # A second collection cannot steal the episode.
    other = "https://www.youtube.com/playlist?list=PLothercollection"
    api_host.stack.video_inspector.collections[other] = video_collection(
        "Other Collection",
        [("Episode One", EPISODE_1, 120.0)],
    )
    conflict_preview = api_host.client.post(
        "/api/intake/inspect", json={"url": other}
    ).json()
    assert conflict_preview["conflict_count"] == 1
    conflict = api_host.client.post("/api/collections", json={"url": other})
    assert conflict.status_code == 201, conflict.text
    assert conflict.json()["skipped_count"] == 1
    assert conflict.json()["added_count"] == 0


def test_collection_delete_modes(api_host):
    _seed_collection(api_host)
    api_host.login()
    created = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    collection_id = created.json()["collection"]["id"]
    item_ids = [item["id"] for item in created.json()["collection"]["items"]]

    ungroup = api_host.client.delete(
        f"/api/collections/{collection_id}?mode=ungroup"
    )
    assert ungroup.status_code == 200, ungroup.text
    assert ungroup.json()["deleted_items"] == 3
    assert api_host.client.get(f"/api/collections/{collection_id}").status_code == 404
    for item_id in item_ids:
        item = api_host.client.get(f"/api/items/{item_id}")
        assert item.status_code == 200
        assert item.json()["collection_id"] is None
        source = json.loads(
            (api_host.config.library_dir / item_id / "source.json").read_text()
        )
        assert "collection" not in source

    created_again = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    collection_id = created_again.json()["collection"]["id"]
    item_ids = [item["id"] for item in created_again.json()["collection"]["items"]]
    deleted = api_host.client.delete(
        f"/api/collections/{collection_id}?mode=delete_items"
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_items"] == 3
    for item_id in item_ids:
        assert api_host.client.get(f"/api/items/{item_id}").status_code == 404


def test_collection_delete_items_resets_consumption(api_host):
    from trove.clock import utc_ms

    _seed_collection(api_host)
    api_host.login()
    created = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    collection_id = created.json()["collection"]["id"]
    item_ids = [item["id"] for item in created.json()["collection"]["items"]]
    now = utc_ms()
    for index, item_id in enumerate(item_ids):
        api_host.runtime.sync.apply_progress(
            item_id,
            position_sec=30.0 + index,
            book_locator=None,
            consumption_state="in_progress",
            client_updated_at=now,
            device_id="test-device",
        )

    deleted = api_host.client.delete(
        f"/api/collections/{collection_id}?mode=delete_items"
    )
    assert deleted.status_code == 200, deleted.text

    readded = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    assert readded.status_code == 201, readded.text
    for item_id in item_ids:
        item = api_host.client.get(f"/api/items/{item_id}").json()
        assert item["consumption_state"] == "unstarted"
        assert item["audio_position_sec"] == 0.0


def test_collection_limit_is_enforced(api_host):
    _seed_collection(api_host)
    api_host.config.max_collection_items = 2
    api_host.login()
    response = api_host.client.post("/api/intake/inspect", json={"url": PLAYLIST})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "collection.too_large"


def test_bilibili_bare_video_with_multiple_parts_is_collection(api_host):
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    api_host.stack.video_inspector.collections[url] = video_collection(
        "Multi Part",
        [
            ("P1", "https://www.bilibili.com/video/BV1xx411c7mD", 60.0),
            ("P2", "https://www.bilibili.com/video/BV1xx411c7mD?p=2", 70.0),
        ],
    )
    api_host.login()
    response = api_host.client.post("/api/intake/inspect", json={"url": url})
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == "collection"
    assert response.json()["episode_count"] == 2


def test_youtube_watch_with_list_is_single_and_warns(api_host):
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234567890"
    canonical = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    api_host.stack.video_inspector.singles[canonical] = VideoInfo(
        is_playlist=False,
        title="Single fixture",
        author="Fixture Author",
        duration_sec=42.0,
    )
    api_host.login()
    response = api_host.client.post("/api/intake/inspect", json={"url": url})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["kind"] == "video"
    assert payload["ignored_playlist"] is True
    assert any(warning["code"] == "link.ignored_playlist" for warning in payload["warnings"])


def test_collection_metadata_is_in_source_package_and_manifest(api_host):
    _seed_collection(api_host)
    api_host.login()
    created = api_host.client.post("/api/collections", json={"url": PLAYLIST})
    item_id = created.json()["collection"]["items"][0]["id"]
    source = json.loads(
        (api_host.config.library_dir / item_id / "source.json").read_text()
    )
    assert source["collection"]["title"] == "Fixture Collection"
    assert source["collection"]["index"] == 1

    manifest = api_host.client.get("/api/sync/manifest?limit=100")
    assert manifest.status_code == 200, manifest.text
    synced = next(
        item for item in manifest.json()["items"] if item["id"] == item_id
    )
    assert synced["collection_id"] == created.json()["collection"]["id"]
    assert synced["collection_title"] == "Fixture Collection"


def test_ebook_url_inspect_add_and_process(host):
    url = "https://example.com/books/aesop.epub"
    host.stack.link_probe.responses[url] = LinkProbeResult(
        content_type="application/epub+zip",
        content_length=12345,
        final_url=url,
    )
    host.login()
    inspected = host.client.post("/api/intake/inspect", json={"url": url})
    assert inspected.status_code == 200, inspected.text
    preview = inspected.json()
    assert preview["kind"] == "ebook"
    assert preview["file_size"] == 12345
    assert preview["title"] == "aesop"

    created = host.client.post(
        "/api/items", json={"kind": "ebook_url", "url": url}
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert payload["source_type"] == "epub_url"
    assert payload["has_book"] is True, payload
    assert payload["processing_state"] == "completed", payload
    assert payload["title"]
    chapter = host.client.get(f"/api/items/{item_id}/book/chapters/0")
    assert chapter.status_code == 200, chapter.text

    repeated = host.client.post(
        "/api/items", json={"kind": "ebook_url", "url": url}
    )
    assert repeated.status_code == 200
    assert repeated.json()["deduplicated"] is True
    assert repeated.json()["item"]["id"] == item_id


def test_ebook_html_and_pdf_are_rejected(api_host):
    api_host.login()
    html_url = "https://example.com/book/12345"
    api_host.stack.link_probe.responses[html_url] = LinkProbeResult(
        content_type="text/html",
        content_length=100,
        final_url=html_url,
    )
    html = api_host.client.post("/api/intake/inspect", json={"url": html_url})
    assert html.status_code == 422, html.text
    assert html.json()["code"] == "link.unsupported"

    pdf_url = "https://example.com/book.pdf"
    api_host.stack.link_probe.responses[pdf_url] = LinkProbeResult(
        content_type="application/pdf",
        content_length=100,
        final_url=pdf_url,
    )
    pdf = api_host.client.post("/api/intake/inspect", json={"url": pdf_url})
    assert pdf.status_code == 422, pdf.text
    assert pdf.json()["code"] == "link.unsupported"
