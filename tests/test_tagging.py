from __future__ import annotations

import pytest

from .conftest import seed_item


def _mark_ai(host, item_id: str, tag_name: str) -> None:
    from sqlalchemy import text

    with host.runtime.sessions() as session:
        session.execute(
            text(
                "UPDATE item_tags SET source = 'ai' WHERE item_id = :item_id "
                "AND tag_id = (SELECT id FROM tags WHERE normalized_name = :name)"
            ),
            {"item_id": item_id, "name": tag_name},
        )
        session.commit()


def test_add_and_remove_tags_updates_sources_search_and_filters(host):
    bundle = seed_item(host, title="Tag CRUD", tags=["AI Tag"])
    _mark_ai(host, bundle.item.id, "ai tag")
    host.login()

    added = host.client.post(f"/api/items/{bundle.item.id}/tags", json={"tag": "#New Tag"})
    assert added.status_code == 200, added.text
    payload = added.json()
    assert payload["tags"] == ["AI Tag", "New Tag"]
    assert {item["name"]: item["source"] for item in payload["tag_items"]} == {
        "AI Tag": "ai",
        "New Tag": "user",
    }

    duplicate = host.client.post(f"/api/items/{bundle.item.id}/tags", json={"tag": "new tag"})
    assert duplicate.status_code == 200
    assert duplicate.json()["tags"] == ["AI Tag", "New Tag"]

    assert host.client.get("/api/search", params={"q": "New"}).json()["count"] == 1
    filtered = host.client.get("/api/items", params={"tag": "new tag"}).json()
    assert filtered["count"] == 1
    assert filtered["items"][0]["id"] == bundle.item.id

    removed = host.client.delete(f"/api/items/{bundle.item.id}/tags/new%20tag")
    assert removed.status_code == 200, removed.text
    assert removed.json()["tags"] == ["AI Tag"]
    assert host.client.get("/api/search", params={"q": "New"}).json()["count"] == 0

    detail = host.client.get(f"/items/{bundle.item.id}")
    assert "AI Tag" in detail.text
    assert "New Tag" not in detail.text


def test_tag_validation_unknown_items_and_tags(host):
    bundle = seed_item(host, title="Tag errors")
    host.login()
    empty = host.client.post(f"/api/items/{bundle.item.id}/tags", json={"tag": "  "})
    assert empty.status_code == 422
    assert empty.json()["details"]["code"] == "tag.empty"
    too_long = host.client.post(
        f"/api/items/{bundle.item.id}/tags", json={"tag": "x" * 65}
    )
    assert too_long.status_code == 422
    assert too_long.json()["details"]["code"] == "tag.too_long"
    missing = host.client.post("/api/items/missing/tags", json={"tag": "x"})
    assert missing.status_code == 404
    unknown_tag = host.client.delete(f"/api/items/{bundle.item.id}/tags/missing")
    assert unknown_tag.status_code == 404
    assert unknown_tag.json()["details"]["code"] == "tag.not_found"


def test_patch_tags_replaces_the_item_tag_set(host):
    bundle = seed_item(host, title="PATCH tags", tags=["old"])
    host.login()
    response = host.client.patch(
        f"/api/items/{bundle.item.id}", json={"tags": ["#New", "new", "Other"]}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["tags"] == ["New", "Other"]
    assert {item["source"] for item in payload["tag_items"]} == {"user"}
    assert host.client.get("/api/search", params={"q": "New"}).json()["count"] == 1
    assert host.client.get("/api/search", params={"q": "old"}).json()["count"] == 0


def test_tag_counts_endpoint(host):
    seed_item(host, title="One", tags=["shared", "solo"])
    seed_item(host, title="Two", tags=["shared"])
    host.login()
    response = host.client.get("/api/tags")
    assert response.status_code == 200
    tags = {entry["name"]: entry["count"] for entry in response.json()["tags"]}
    assert tags["shared"] == 2
    assert tags["solo"] == 1


def test_tag_edit_via_html_redirects_to_detail(host):
    bundle = seed_item(host, title="HTML tags")
    host.login()
    response = host.client.post(
        f"/items/{bundle.item.id}/tags/add",
        data={"tag": "手动标签"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = host.client.get(f"/items/{bundle.item.id}")
    assert "手动标签" in detail.text
    deleted = host.client.post(
        f"/items/{bundle.item.id}/tags/delete",
        data={"tag": "手动标签"},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert "手动标签" not in host.client.get(f"/items/{bundle.item.id}").text


def test_unauthenticated_users_cannot_edit_tags(api_host):
    bundle = seed_item(api_host, title="Auth tags")
    response = api_host.client.post(f"/api/items/{bundle.item.id}/tags", json={"tag": "x"})
    assert response.status_code == 401


@pytest.mark.ffmpeg
def test_user_can_delete_ai_tag_and_reprocessing_readds_it(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    item_id = response.json()["item"]["id"]
    payload = host.wait_for_item(item_id)
    assert set(payload["tags"]) == {"智能体", "记忆", "LLM"}
    assert {entry["source"] for entry in payload["tag_items"]} == {"ai"}

    calls_before = len(host.stack.organizer.calls)
    deleted = host.client.delete(f"/api/items/{item_id}/tags/记忆")
    assert deleted.status_code == 200
    assert "记忆" not in deleted.json()["tags"]
    assert len(host.stack.organizer.calls) == calls_before

    reprocess = host.client.post(
        f"/api/items/{item_id}/reprocess", json={"from_stage": "organizing"}
    )
    assert reprocess.status_code == 202
    payload = host.wait_for_item(item_id)
    assert "记忆" in payload["tags"]
    assert {entry["source"] for entry in payload["tag_items"]} == {"ai"}


@pytest.mark.ffmpeg
def test_reprocessing_preserves_user_tags(host):
    host.login()
    response = host.client.post(
        "/api/items", json={"kind": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    item_id = response.json()["item"]["id"]
    host.wait_for_item(item_id)
    host.client.post(f"/api/items/{item_id}/tags", json={"tag": "我自己的标签"})

    host.stack.organizer.tags = ["新标签"]
    host.client.post(f"/api/items/{item_id}/reprocess", json={"from_stage": "organizing"})
    payload = host.wait_for_item(item_id)
    assert "我自己的标签" in payload["tags"]
    assert "新标签" in payload["tags"]
    assert "智能体" not in payload["tags"]
    sources = {entry["name"]: entry["source"] for entry in payload["tag_items"]}
    assert sources["我自己的标签"] == "user"
    assert sources["新标签"] == "ai"
