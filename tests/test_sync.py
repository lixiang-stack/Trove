from __future__ import annotations

import json

from trove.clock import utc_ms
from trove.db.models import Item

from .conftest import seed_item


def _manifest(host, cursor: str | None = None, limit: int | None = None) -> dict:
    params: dict[str, str | int] = {}
    if cursor is not None:
        params["cursor"] = cursor
    if limit is not None:
        params["limit"] = limit
    response = host.client.get("/api/sync/manifest", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _state(host, cursor: str | None = None, limit: int | None = None) -> dict:
    params: dict[str, str | int] = {}
    if cursor is not None:
        params["cursor"] = cursor
    if limit is not None:
        params["limit"] = limit
    response = host.client.get("/api/sync/state", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_manifest_returns_compact_items_files_and_cursor(host):
    bundle = seed_item(
        host,
        title="Manifest Item",
        author="Author",
        summary="Summary",
        tags=["Memory", "AI"],
    )
    host.login()
    payload = _manifest(host)
    assert payload["epoch"]
    assert payload["has_more"] is False
    assert payload["next_cursor"]
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == bundle.item.id
    assert item["version"] == bundle.item.version
    assert item["title"] == "Manifest Item"
    assert item["tags"] == ["AI", "Memory"]
    assert item["processing_state"] == "completed"
    assert item["has_audio"] is True
    assert item["has_book"] is False
    assert item["files"] == [
        {
            "kind": "audio",
            "sha256": bundle.artifacts[0].sha256,
            "size": bundle.artifacts[0].size,
            "mime": "audio/mp4",
            "version": bundle.item.version,
            "url": f"/api/items/{bundle.item.id}/files/audio",
        }
    ]
    assert "run" not in item
    assert "steps" not in json.dumps(item)
    assert "log_tail" not in json.dumps(item)
    assert payload["tombstones"] == []


def test_manifest_paginates_without_duplicates_or_gaps(host):
    for index in range(5):
        seed_item(host, title=f"Item {index}", with_audio=False, run_state=None)
    host.login()
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        payload = _manifest(host, cursor=cursor, limit=2)
        pages += 1
        seen.extend(item["id"] for item in payload["items"])
        if not payload["has_more"]:
            assert payload["next_cursor"] == cursor or payload["items"]
            break
        cursor = payload["next_cursor"]
    assert pages == 3
    assert len(seen) == 5
    assert len(set(seen)) == 5


def test_manifest_is_incremental_and_state_does_not_bump_content(host):
    first = seed_item(host, title="First", with_audio=False, run_state=None)
    second = seed_item(host, title="Second", with_audio=False, run_state=None)
    host.login()
    initial = _manifest(host)
    assert {item["id"] for item in initial["items"]} == {first.item.id, second.item.id}
    cursor = initial["next_cursor"]

    response = host.client.put(
        f"/api/items/{first.item.id}/progress", json={"position_sec": 1.0}
    )
    assert response.status_code == 200, response.text

    incremental = _manifest(host, cursor=cursor)
    assert incremental["items"] == []
    assert incremental["next_cursor"] == cursor

    state = _state(host)
    state_item = next(item for item in state["items"] if item["id"] == first.item.id)
    assert state_item["audio_position_sec"] == 1.0
    assert state_item["state_seq"] > 0


def test_state_sync_is_incremental(host):
    first = seed_item(host, title="First", position=1.0)
    second = seed_item(host, title="Second", position=2.0)
    host.login()
    initial = _state(host)
    assert {item["id"] for item in initial["items"]} == {first.item.id, second.item.id}
    cursor = initial["next_cursor"]

    host.client.put(f"/api/items/{first.item.id}/progress", json={"position_sec": 1.5})
    incremental = _state(host, cursor=cursor)
    assert [item["id"] for item in incremental["items"]] == [first.item.id]
    assert incremental["items"][0]["audio_position_sec"] == 1.5


def test_invalid_and_future_cursors_are_rejected(host):
    seed_item(host, title="Cursor", with_audio=False, run_state=None)
    host.login()
    invalid = host.client.get("/api/sync/manifest", params={"cursor": "nope"})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "sync.cursor_invalid"

    future = host.client.get("/api/sync/manifest", params={"cursor": "999999"})
    assert future.status_code == 422
    assert future.json()["code"] == "sync.cursor_invalid"

    negative = host.client.get("/api/sync/state", params={"cursor": "-1"})
    assert negative.status_code == 422
    assert negative.json()["code"] == "sync.cursor_invalid"


def test_epoch_changes_after_reset(host):
    seed_item(host, title="Epoch", with_audio=False, run_state=None)
    host.login()
    before = _manifest(host)["epoch"]
    from trove.db.sequences import reset_epoch

    with host.runtime.sessions() as session:
        after = reset_epoch(session)
    assert after != before
    assert _manifest(host)["epoch"] == after


def test_manifest_filters_tombstones_into_separate_list(host):
    bundle = seed_item(host, title="Gone", with_audio=False, run_state=None)
    host.login()
    cursor = _manifest(host)["next_cursor"]
    assert host.client.delete(f"/api/items/{bundle.item.id}").status_code == 204
    payload = _manifest(host, cursor=cursor)
    assert payload["items"] == []
    assert len(payload["tombstones"]) == 1
    tombstone = payload["tombstones"][0]
    assert tombstone["id"] == bundle.item.id
    assert tombstone["version"] == bundle.item.version + 1
    assert tombstone["deleted_at"] > 0
    assert tombstone["epoch"] == payload["epoch"]


def test_thousand_item_seed_paginates_in_order(host):
    now = utc_ms()
    with host.runtime.sessions() as session:
        for index in range(1000):
            session.add(
                Item(
                    id=f"item-{index:04d}",
                    source_key=f"bulk-{index:04d}",
                    source_type="local_audio",
                    platform="local",
                    title=f"Bulk {index:04d}",
                    fetched_at=now,
                    created_at=now + index,
                    updated_at=now + index,
                )
            )
        session.commit()
    host.login()
    seen: list[str] = []
    cursor = None
    while True:
        payload = _manifest(host, cursor=cursor, limit=100)
        seen.extend(item["id"] for item in payload["items"])
        if not payload["has_more"]:
            break
        cursor = payload["next_cursor"]
    assert len(seen) == 1000
    assert len(set(seen)) == 1000
    assert seen == sorted(seen)
