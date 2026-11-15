from __future__ import annotations

import io
import zipfile

from .conftest import seed_item


def _add_video(host, url: str):
    return host.runtime.intake.add_video_url(url)


def test_delete_filters_library_search_continue_and_export(host):
    bundle = seed_item(host, title="Visible before delete", position=1.0)
    host.runtime.search_index.index_item(bundle.item.id)
    host.login()
    assert host.client.get("/api/search", params={"q": "Visible"}).json()["results"]
    assert host.client.get("/api/continue").json()["entries"]

    assert host.client.delete(f"/api/items/{bundle.item.id}").status_code == 204

    library = host.client.get("/api/items").json()
    assert library["items"] == []
    assert host.client.get("/api/search", params={"q": "Visible"}).json()["results"] == []
    assert host.client.get("/api/continue").json()["entries"] == []
    export = host.client.get("/api/export")
    assert export.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        index = archive.read("index.md").decode("utf-8")
    assert "Visible before delete" not in index
    assert "Items: 0" in index


def test_readding_same_source_revives_same_item_with_new_run(host):
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    first, deduplicated = _add_video(host, url)
    assert deduplicated is False
    first_run = first.run
    assert first_run is not None

    host.login()
    initial = host.client.get("/api/sync/manifest").json()
    cursor = initial["next_cursor"]
    assert host.client.delete(f"/api/items/{first.item.id}").status_code == 204
    assert host.client.get(f"/api/items/{first.item.id}").status_code == 404
    deleted_payload = host.client.get(
        "/api/sync/manifest", params={"cursor": cursor}
    ).json()
    assert [row["id"] for row in deleted_payload["tombstones"]] == [first.item.id]

    second, deduplicated = _add_video(host, url)
    assert deduplicated is False
    assert second.item.id == first.item.id
    assert second.run is not None
    assert second.run.id != first_run.id
    assert second.item.version > first.item.version

    payload = host.client.get(
        "/api/sync/manifest", params={"cursor": deleted_payload["next_cursor"]}
    ).json()
    assert payload["tombstones"] == []
    assert [row["id"] for row in payload["items"]] == [first.item.id]


def test_duplicate_add_still_deduplicates_visible_items(host):
    url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
    first, deduplicated = _add_video(host, url)
    assert deduplicated is False
    second, deduplicated = _add_video(host, url)
    assert deduplicated is True
    assert second.item.id == first.item.id
    assert second.run.id == first.run.id


def test_index_rebuild_skips_tombstones(host):
    bundle = seed_item(host, title="Rebuild tombstone", with_audio=False, run_state=None)
    host.login()
    assert host.client.delete(f"/api/items/{bundle.item.id}").status_code == 204
    assert host.runtime.search_index.rebuild() == 0
    status = host.runtime.search.index_status()
    assert status.items == []
